"""Phase 9 API tests: chat, quotes, enquiries, tours, bookings, errors, log masking.

Each test runs in a database transaction that is rolled back. The chat graph uses scripted
fake models (no Gemini calls) and tracing is off.
"""

from __future__ import annotations

import logging
import json
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
    assert [c["type"] for c in body["ui"]] == ["tour_card", "price_breakdown", "booking_form"]
    assert body["ui"][1] == {"type": "price_breakdown", "quote_id": body["quote_id"]}   # no price in the payload
    assert body["ui"][2]["quote_id"] == body["quote_id"] and body["ui"][0]["tour_id"] == "T01"
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
    card = next(c for c in second["ui"] if c["type"] == "price_breakdown")
    assert card["quote_id"] == second["quote_id"]
    assert api.client.get(f"/api/v1/quotes/{card['quote_id']}").json()["price_usd"] == 2965
    history = api.client.get(f"/api/v1/conversations/{first['conversation_id']}").json()["messages"]
    assert [m["role"] for m in history] == ["traveller", "mira", "traveller", "mira"]
    # each reply comes back with its own cards, so a reloaded chat looks the same
    assert history[3]["ui"] == second["ui"] and history[0]["ui"] == history[2]["ui"] == []


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


# ---- R6: no guess, a specialist confirms, staff get a flag ------------------------------

EARLY_BIRD = "Can I book the Popular Stays Winter 2023/24 Early Bird Deal for 2 adults from 3 May 2027? How much?"
TRANSFER = "How much is an airport transfer from CMB to Kandy for 2 people?"


def _no_price_enquiry(db, body, flag):
    assert body["enquiry_id"], "no enquiry saved for staff"
    enquiry = db.get(Enquiry, uuid.UUID(body["enquiry_id"]))
    assert enquiry.kind == "no_price" and flag in enquiry.flags
    assert all(c["type"] not in ("price_breakdown", "booking_form") for c in body["ui"])
    assert any(c["type"] == "specialist_notice" and c["reason"] == "no_price" for c in body["ui"])
    return enquiry


def test_expired_offer_by_name_is_flagged_for_staff(api, db):
    mention = "Popular Stays Winter 2023/24 Early Bird Deal"
    api.use(FakeModel(RouterDecision=[R("book", mention)],
                      TripDetails=[T(tour_mention=mention, adults=2, start_date=date(2027, 5, 3))]))
    body = api.chat(EARLY_BIRD).json()
    _no_price_enquiry(db, body, "stale_tour")
    assert "USD" not in body["message"] and "specialist" in body["message"]


def test_expired_offer_is_never_suggested(base):
    from app.graph.tours import suggest_tours
    for interests in (["bird"], ["stay"], ["winter"], []):
        assert "T14" not in [c["tour_id"] for c in suggest_tours(base.tours, interests=interests,
                                                                 destinations=[], days=None)]


def test_service_price_is_not_guessed_and_is_flagged(api, db):
    api.use(FakeModel(RouterDecision=[R("quote")], TripDetails=[T(adults=2, destinations=["Kandy"])]))
    body = api.chat(TRANSFER).json()
    enquiry = _no_price_enquiry(db, body, "unpriced_service")
    assert "airport transfer" in body["message"] and "won't guess" in body["message"]
    assert "age" not in body["message"] and body["quote_id"] is None
    assert "airport transfer" in enquiry.notes                 # staff see what was asked


@pytest.mark.parametrize("message, flag", [(EARLY_BIRD, "stale_tour"), (TRANSFER, "unpriced_service")])
def test_no_price_cases_are_flagged_when_gemini_is_down(api, db, message, flag):
    api.use(FakeModel())                                       # every model call fails: rules only
    _no_price_enquiry(db, api.chat(message).json(), flag)


@pytest.mark.parametrize("message, mention", [
    ("Do your tours include airport transfers?", None),                     # no price asked
    ("How much is the Kandy City Tour for 2 adults on 3 May 2027? Is the transfer included?",
     "Kandy City Tour"),                                                     # a tour named: the tour wins
])
def test_tour_questions_are_not_mistaken_for_services(base, message, mention):
    from langchain_core.messages import HumanMessage

    from app.graph.nodes import Nodes
    from app.graph.state import PER_TURN_DEFAULTS
    state = {**PER_TURN_DEFAULTS, "messages": [HumanMessage(content=message)], "questions_asked": 0,
             "intent": "quote" if mention else "tour_info", "tour_mention": mention}
    out = Nodes(base).route(state)
    assert out["action"] != "handoff" and not out.get("unpriced_service")


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


def card(number="4242 4242 4242 4242", **over):
    """A full mock card, as the booking form sends it."""
    return {"holder": "Test Traveller", "brand": "visa", "number": number, "exp_month": 12, "exp_year": 28,
            "cvc": "123", **over}


def book(api, quote_id, card_number="4242 4242 4242 4242", **over):
    return api.client.post("/api/v1/bookings", json={"quote_id": str(quote_id), "contact": CONTACT,
                                                     "card": card(card_number, **over)})


def test_booking_succeeds(api, db):
    quote = quote_s02(api, db)
    r = book(api, quote.id)
    body = r.json()
    assert r.status_code == 200 and body["status"] == "confirmed" and body["amount_charged_usd"] == 315
    assert body["payment_reference"].startswith("mock_ch_") and "demo" in body["message"]
    booking = db.get(Booking, uuid.UUID(body["booking_id"]))
    assert booking.status == "confirmed"
    assert (booking.card_brand, booking.card_last4) == ("visa", "4242") and body["card"] == "Visa ending 4242"
    enquiry = db.get(Enquiry, uuid.UUID(body["enquiry_id"]))
    assert enquiry.contact["email"] == CONTACT["email"] and "Booked (mock)" in enquiry.notes
    again = book(api, quote.id)
    assert again.status_code == 409 and again.json()["error"] == "conflict"


def test_test_card_fails_politely_and_saves_an_enquiry(api, db):
    quote = quote_s02(api, db)
    r = book(api, quote.id, "4000 0000 0000 0002")
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
    body = book(api, quote.id, "4242 4242 4242 4241").json()                 # fails the Luhn check
    assert body["status"] == "payment_failed" and body["next_steps"] == ["retry"] and body["field"] == "number"
    assert book(api, quote.id, "1234 5678 9012 ABCD").status_code == 422     # not even digits


@pytest.mark.parametrize("over, field, words", [
    ({"brand": "mastercard"}, "brand", "isn't a Mastercard card"),
    ({"exp_month": 10, "exp_year": 26}, "expiry", "expired"),               # MIRA_TODAY is 2026-11-19
    ({"exp_year": 2060}, "expiry", "MM/YY"),
    ({"cvc": "1234"}, "cvc", "3 digits"),
    ({"holder": "12 34"}, "holder", "name"),
])
def test_card_details_are_checked_like_a_real_card(api, db, over, field, words):
    quote = quote_s02(api, db)
    body = book(api, quote.id, **over).json()
    assert body["status"] == "payment_failed" and body["field"] == field and words in body["message"]
    assert "Nothing was charged" in body["message"] and body.get("enquiry_id") is None


def test_other_card_types_and_this_month_expiry_work(api, db):
    assert book(api, quote_s02(api, db).id, "5555 5555 5555 4444", brand="mastercard").json()["card"] \
        == "Mastercard ending 4444"
    body = book(api, quote_s02(api, db).id, "3782 822463 10005", brand="amex", cvc="1234").json()
    assert body["status"] == "confirmed" and body["card"] == "American Express ending 0005"
    assert book(api, quote_s02(api, db).id, exp_month=11, exp_year=2026).json()["status"] == "confirmed"
    amex_short = book(api, quote_s02(api, db).id, "3782 822463 10005", brand="amex", cvc="123").json()
    assert amex_short["field"] == "cvc" and "front" in amex_short["message"]


def test_card_is_never_stored_or_echoed(api, db, caplog):
    quote = quote_s02(api, db)
    body = book(api, quote.id, "4000 0000 0000 0002", cvc="987").json()
    enquiry = db.get(Enquiry, uuid.UUID(body["enquiry_id"]))
    booking = db.get(Booking, uuid.UUID(body["booking_id"]))
    stored = str(enquiry.contact) + str(enquiry.notes) + str(vars(booking))
    assert "4000000000000002" not in stored and "4000 0000" not in stored and "987" not in stored
    assert booking.card_last4 == "0002"
    assert "4000 0000 0000 0002" not in caplog.text and "987" not in caplog.text


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
                                                  "card": card("4242424242424242")})
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


# ---- 11.1 AG-UI-style event stream ---------------------------------------------------------

def stream(api, message, **kw):
    r = api.client.post("/api/v1/chat/stream", json={"message": message, **kw})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    return [json.loads(line[6:]) for line in r.text.splitlines() if line.startswith("data: ")]


def test_stream_sends_steps_text_components_and_the_result(api, db):
    events = stream(api.use(s02_model()), S02)
    types = [e["type"] for e in events]
    assert types[0] == "RUN_STARTED" and types[-1] == "RUN_FINISHED"
    steps = [e["stepName"] for e in events if e["type"] == "STEP_FINISHED"]
    assert steps[:2] == ["load_visitor", "guard"] and "price" in steps and steps[-1] == "build_ui"
    text = next(e for e in events if e["type"] == "TEXT_MESSAGE_CONTENT")["delta"]
    assert "USD 315" in text
    ui = [e["value"]["type"] for e in events if e["type"] == "CUSTOM" and e["name"] == "ui_component"]
    assert ui == ["tour_card", "price_breakdown", "booking_form"]
    result = events[-1]["result"]
    assert result["message"] == text and db.get(Quote, uuid.UUID(result["quote_id"])).price_usd == 315
    assert events[0]["threadId"] == result["conversation_id"]


def test_stream_failure_is_a_polite_handoff(api, monkeypatch):
    api.use(FakeModel())

    def boom(*a, **kw):
        raise RuntimeError("graph exploded")
    monkeypatch.setattr("app.api.chat.run_turn", boom)
    events = stream(api, "Hello")
    result = events[-1]["result"]
    assert events[-1]["type"] == "RUN_FINISHED" and "travel specialists" in result["message"]
    assert result["ui"][0]["type"] == "specialist_notice" and result["ui"][0]["enquiry_id"] == result["enquiry_id"]
