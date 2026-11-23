"""Phase 9 API tests: chat, quotes, enquiries, tours, bookings, errors, log masking.

Each test runs in a database transaction that is rolled back. The chat graph uses scripted
fake models (no Gemini calls) and tracing is off.
"""

from __future__ import annotations

import logging
import uuid
from contextlib import contextmanager
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_chat_graph, get_db
from app.db.models import Booking, Enquiry, Quote
from app.db.session import check_database, create_tables, get_engine
from app.graph.build import build_graph
from app.graph.nodes import Deps
from app.main import app
from tests.unit.test_graph import FakeModel, R, T

TODAY = date(2026, 11, 19)
S02 = "How much is the Sigiriya and Minneriya day tour from Kandy for 2 adults on 10 January 2027?"
COST_WORDS = ("cost", "margin", "gp_pct", "fx", "rate_rows", "vehicle", "lkr")


@pytest.fixture(scope="module")
def engine():
    eng = get_engine()
    if not check_database(eng):
        pytest.skip("database not reachable (start it with: docker compose up -d db)")
    create_tables(eng)
    return eng


@pytest.fixture
def db(engine):
    with engine.connect() as conn:
        outer = conn.begin()
        session = Session(bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False)
        try:
            yield session
        finally:
            session.close()
            outer.rollback()


@pytest.fixture(scope="module")
def base():
    return Deps.default(today=TODAY, session_scope=None)


@pytest.fixture
def api(db, base, monkeypatch):
    """A client whose chat graph uses `api.model` (set per test) and the test session."""
    monkeypatch.setattr("app.graph.tracing.get_langfuse", lambda: None)
    monkeypatch.setattr("app.llm.structured._sleep", lambda s: None)

    @contextmanager
    def scope():
        yield db
        db.flush()

    class Api:
        model = FakeModel()
        graph = None

        def chat(self, message, conversation_id=None, **kw):
            body = {"message": message, **kw}
            if conversation_id:
                body["conversation_id"] = str(conversation_id)
            return client.post("/api/v1/chat", json=body)

        def use(self, model):
            self.model = model
            deps = Deps(today=TODAY, settings=base.settings, rates=base.rates, content=base.content,
                        brand=base.brand, tours=base.tours, fast_model=model, strong_model=model,
                        session_scope=scope)
            self.graph = build_graph(deps)
            return self

    a = Api()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_chat_graph] = lambda: a.graph
    client = TestClient(app, raise_server_exceptions=False)
    a.client = client
    yield a
    app.dependency_overrides.clear()


def s02_model():
    return FakeModel(RouterDecision=[R("quote", "Sigiriya and Minneriya day tour from Kandy")],
                     TripDetails=[T(tour_mention="Sigiriya and Minneriya day tour from Kandy",
                                    start_date=date(2027, 1, 10), adults=2)])


def quote_s02(api, db) -> Quote:
    r = api.use(s02_model()).chat(S02)
    assert r.status_code == 200
    return db.get(Quote, uuid.UUID(r.json()["quote_id"]))


# ---- 9.2 / 9.3 / 9.4 chat + persistence ---------------------------------------------------

def test_chat_s02_saves_quote_and_enquiry(api, db):
    r = api.use(s02_model()).chat(S02)
    body = r.json()
    assert r.status_code == 200 and "USD 315" in body["message"]
    card = next(c for c in body["ui"] if c["type"] == "quote_card")
    assert card["quote"]["price_usd"] == 315 and card["quote_id"] == body["quote_id"]
    quote = db.get(Quote, uuid.UUID(body["quote_id"]))
    assert quote.status == "ok" and quote.price_usd == 315 and quote.cost_usd is not None   # staff fields kept
    assert str(quote.conversation_id) == body["conversation_id"]
    enquiry = db.get(Enquiry, uuid.UUID(body["enquiry_id"]))
    assert enquiry.kind == "quote" and enquiry.quote_id == quote.id
    assert not any(w in str(body).lower() for w in COST_WORDS)


def test_same_conversation_keeps_context(api):
    api.use(FakeModel(RouterDecision=[R("quote"), R("quote", "Cultural Triangle package")],
                      TripDetails=[T(adults=2, child_ages=[7, 10]),
                                   T(adults=2, child_ages=[7, 10], tour_mention="Cultural Triangle package",
                                     start_date=date(2027, 4, 12))]))
    first = api.chat("We're 2 adults and 2 kids aged 7 and 10.").json()
    second = api.chat("We'd like the Cultural Triangle package starting 12 April 2027.",
                      conversation_id=first["conversation_id"]).json()
    assert second["conversation_id"] == first["conversation_id"]
    assert second["visitor_id"] == first["visitor_id"]
    assert next(c for c in second["ui"] if c["type"] == "quote_card")["quote"]["price_usd"] == 2965
    history = api.client.get(f"/api/v1/conversations/{first['conversation_id']}").json()["messages"]
    assert [m["role"] for m in history] == ["traveller", "mira", "traveller", "mira"]


def test_s04_saves_a_flagged_no_price_enquiry(api, db):
    api.use(FakeModel(RouterDecision=[R("quote", "Treasures of Sri Lanka")],
                      TripDetails=[T(tour_mention="Treasures of Sri Lanka", start_date=date(2027, 4, 10), adults=1)]))
    body = api.chat("I'm travelling solo. Price for Treasures of Sri Lanka starting 10 April 2027?").json()
    assert body["quote_id"] and "USD" not in body["message"]
    quote = db.get(Quote, uuid.UUID(body["quote_id"]))
    assert quote.status == "needs_specialist" and quote.price_usd is None
    enquiry = db.get(Enquiry, uuid.UUID(body["enquiry_id"]))
    assert enquiry.kind == "no_price" and "missing_rate" in enquiry.flags


def test_unknown_tour_saves_a_custom_enquiry(api, db):
    api.use(FakeModel(RouterDecision=[R("quote", "Adam's Peak sunrise climb")],
                      TripDetails=[T(tour_mention="Adam's Peak sunrise climb")]))
    body = api.chat("Do you do an Adam's Peak sunrise climb?").json()
    enquiry = db.get(Enquiry, uuid.UUID(body["enquiry_id"]))
    assert enquiry.kind == "custom" and "custom_request" in enquiry.flags and body["quote_id"] is None


def test_trace_id_is_stored_on_quote_and_enquiry(db, base):
    from langchain_core.messages import HumanMessage

    from app.graph.persist import persist_turn
    state = {"quote_request": {"tour_id": "T01", "start_date": "2027-01-10", "adults": 2, "child_ages": []},
             "trace_id": "a" * 32, "flags": [], "messages": [HumanMessage(content="x")]}
    out = persist_turn(db, state, base)
    assert db.get(Quote, uuid.UUID(out["quote_id"])).trace_id == "a" * 32
    assert db.get(Enquiry, uuid.UUID(out["enquiry_id"])).trace_id == "a" * 32


def test_graph_failure_is_a_polite_handoff(api, db, monkeypatch):
    api.use(FakeModel())

    def boom(*a, **kw):
        raise RuntimeError("graph exploded")
    monkeypatch.setattr("app.api.chat.run_turn", boom)
    r = api.chat("Hello, my email is a@b.com")
    assert r.status_code == 200 and "travel specialists" in r.json()["message"]
    enquiry = db.get(Enquiry, uuid.UUID(r.json()["enquiry_id"]))
    assert "chat_error" in enquiry.flags and "a@b.com" not in (enquiry.notes or "")


def test_unknown_conversation_starts_a_new_one(api):
    api.use(FakeModel(RouterDecision=[R("out_of_scope")]))
    missing = uuid.uuid4()
    body = api.chat("write me a poem", conversation_id=missing).json()
    assert body["conversation_id"] != str(missing)


# ---- 9.5 quotes --------------------------------------------------------------------------

def test_get_quote_has_public_fields_only(api, db):
    quote = quote_s02(api, db)
    r = api.client.get(f"/api/v1/quotes/{quote.id}")
    assert r.status_code == 200 and r.json()["price_usd"] == 315
    assert not any(w in k.lower() for k in r.json() for w in COST_WORDS)


def test_unknown_quote_is_a_friendly_404(api):
    r = api.client.get(f"/api/v1/quotes/{uuid.uuid4()}")
    assert r.status_code == 404 and r.json()["error"] == "not_found" and "quote" in r.json()["message"]


def test_direct_quote_uses_the_engine(api, db):
    r = api.client.post("/api/v1/quotes", json={"tour_id": "T09", "start_date": "2027-04-12", "adults": 2,
                                                "child_ages": [7, 10]})
    body = r.json()
    assert (body["status"], body["quote"]["price_usd"], body["quote"]["deposit_usd"]) == ("ok", 2965, 742)
    assert db.scalar(select(Enquiry.kind).where(Enquiry.quote_id == uuid.UUID(body["quote_id"]))) == "quote"
    refused = api.client.post("/api/v1/quotes", json={"tour_id": "T12", "start_date": "2027-04-10",
                                                      "adults": 1}).json()
    assert refused["status"] == "needs_specialist" and refused["quote"] is None and refused["messages"]


# ---- 9.6 enquiries -----------------------------------------------------------------------

def test_enquiry_from_the_ui_is_saved_with_contact(api, db):
    r = api.client.post("/api/v1/enquiries", json={
        "kind": "custom", "notes": "A 10-day honeymoon with tea country",
        "contact": {"name": "Test Traveller", "email": "traveller@example.com"}})
    assert r.status_code == 200
    enquiry = db.get(Enquiry, uuid.UUID(r.json()["enquiry_id"]))
    assert enquiry.contact["email"] == "traveller@example.com" and "from_traveller" in enquiry.flags


def test_enquiry_rejects_a_bad_email(api):
    r = api.client.post("/api/v1/enquiries", json={"contact": {"name": "X", "email": "not-an-email"}})
    assert r.status_code == 422 and r.json()["fields"] == ["contact.email"]


# ---- 9.7 tours ---------------------------------------------------------------------------

def test_published_tour_without_prices(api):
    body = api.client.get("/api/v1/tours/T09").json()
    assert body["title"] == "Cultural Triangle Sri Lanka Package" and body["bookable"] is True
    assert body["itinerary"] and "USD" not in body["body"] and "560" not in body["body"]


@pytest.mark.parametrize("tour_id", ["T15", "T99", "nonsense"])
def test_draft_or_unknown_tour_is_404(api, tour_id):
    r = api.client.get(f"/api/v1/tours/{tour_id}")
    assert r.status_code == 404 and r.json()["error"] == "not_found"


def test_tour_id_is_normalised(api):
    assert api.client.get("/api/v1/tours/t-9").json()["tour_id"] == "T09"


# ---- 9.8 bookings ------------------------------------------------------------------------

CONTACT = {"name": "Test Traveller", "email": "traveller@example.com"}


def book(api, quote_id, card="4242 4242 4242 4242"):
    return api.client.post("/api/v1/bookings", json={"quote_id": str(quote_id), "contact": CONTACT,
                                                     "card_number": card})


def test_booking_succeeds(api, db):
    quote = quote_s02(api, db)
    r = book(api, quote.id)
    body = r.json()
    assert r.status_code == 200 and body["status"] == "confirmed" and body["amount_charged_usd"] == 315
    assert body["payment_reference"].startswith("mock_ch_") and "demo" in body["message"]
    booking = db.get(Booking, uuid.UUID(body["booking_id"]))
    assert booking.status == "confirmed"
    enquiry = db.get(Enquiry, uuid.UUID(body["enquiry_id"]))
    assert enquiry.contact["email"] == CONTACT["email"] and "Booked (mock)" in enquiry.notes
    again = book(api, quote.id)
    assert again.status_code == 409 and again.json()["error"] == "conflict"


def test_test_card_fails_politely_and_saves_an_enquiry(api, db):
    quote = quote_s02(api, db)
    r = book(api, quote.id, card="4000 0000 0000 0002")
    body = r.json()
    assert r.status_code == 200 and body["status"] == "payment_failed"
    assert "Nothing was charged" in body["message"]
    assert body["next_steps"] == ["retry", "payment_link", "enquiry_saved"]
    enquiry = db.get(Enquiry, uuid.UUID(body["enquiry_id"]))
    assert enquiry.kind == "booking_failed" and "card_declined" in enquiry.flags
    assert "4000" not in str(enquiry.contact) + str(enquiry.notes)            # card never stored
    assert book(api, quote.id).json()["status"] == "confirmed"                # retry works


def test_mock_payment_fail_flag(api, db, monkeypatch):
    quote = quote_s02(api, db)
    monkeypatch.setattr("app.booking.mock_payment.get_settings",
                        lambda: type("S", (), {"mock_payment_fail": True})())
    body = book(api, quote.id).json()
    assert body["status"] == "payment_failed" and "provider_unavailable" in \
        db.get(Enquiry, uuid.UUID(body["enquiry_id"])).flags


def test_bad_card_number_asks_to_retry(api, db):
    quote = quote_s02(api, db)
    body = book(api, quote.id, card="1234 5678 9012 ABCD").json()
    assert body["status"] == "payment_failed" and body["next_steps"] == ["retry"]


def test_no_price_quote_cannot_be_booked(api, db):
    refused = api.client.post("/api/v1/quotes", json={"tour_id": "T12", "start_date": "2027-04-10",
                                                      "adults": 1}).json()
    r = book(api, refused["quote_id"])
    assert r.status_code == 409 and "specialist" in r.json()["message"]


def test_changed_price_is_not_charged(api, db):
    quote = quote_s02(api, db)
    quote.price_usd = 300                      # as if the rates changed since the quote
    db.flush()
    body = book(api, quote.id).json()
    assert body["status"] == "price_changed" and body["next_steps"] == ["new_quote"]
    assert db.scalar(select(Booking.id).where(Booking.quote_id == quote.id)) is None


def test_validation_error_never_echoes_the_card(api):
    r = api.client.post("/api/v1/bookings", json={"quote_id": "not-a-uuid", "contact": CONTACT,
                                                  "card_number": "4242424242424242"})
    assert r.status_code == 422 and "4242" not in r.text and "quote_id" in r.json()["fields"]


# ---- 9.9 / 9.10 errors and logs ----------------------------------------------------------

def test_unhandled_error_is_friendly_with_no_trace(api, monkeypatch):
    def boom(*a, **kw):
        raise ValueError("secret internal detail")
    monkeypatch.setattr("app.api.quotes.get_public_quote", boom)
    r = api.client.get(f"/api/v1/quotes/{uuid.uuid4()}")
    assert r.status_code == 500 and r.json()["error"] == "internal_error"
    assert "secret" not in r.text and "Traceback" not in r.text


def test_logs_mask_personal_data(caplog):
    from app.core.logging import install_log_masking
    install_log_masking()
    with caplog.at_level(logging.INFO, logger="mira.test"):
        logging.getLogger("mira.test").info("contact %s or %s, card %s", "a@b.com", "+94 77 123 4567",
                                            "4111 1111 1111 1111")
    text = caplog.records[-1].getMessage()
    assert text == "contact [email] or [phone], card [card number]"
