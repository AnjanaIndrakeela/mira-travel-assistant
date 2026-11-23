"""Step 5.12: save_quote, get_public_quote, create_enquiry against the db container."""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.db.models import Conversation, Enquiry, Quote, Visitor
from app.db.repo import create_enquiry, get_public_quote, save_quote
from app.pricing import QuoteRequest, calculate_quote

TODAY = date(2026, 11, 19)


def _quote(tour, start, adults, ages=()):
    return calculate_quote(QuoteRequest(tour_id=tour, start_date=start, adults=adults, child_ages=ages),
                           today=TODAY)


@pytest.fixture
def conversation(db):
    v = Visitor(party={"adults": 2, "child_ages": [7, 10]}, traveller_type="family")
    db.add(v)
    db.flush()
    c = Conversation(visitor_id=v.id, thread_id=f"test-{uuid.uuid4().hex}")
    db.add(c)
    db.flush()
    return c


def test_save_ok_quote_keeps_public_and_staff_fields(db, conversation):
    result = _quote("T09", date(2027, 4, 12), 2, (7, 10))
    row = save_quote(db, result, conversation_id=conversation.id, trace_id="trace-s03")
    db.expire_all()
    row = db.get(Quote, row.id)
    assert (row.status, row.price_usd, row.deposit_usd, row.balance_usd) == ("ok", 2965, 742, 2223)
    assert row.balance_due == date(2027, 3, 13) and row.trace_id == "trace-s03"
    assert row.child_ages == [7, 10] and row.party_children == 2
    assert row.cost_lkr == Decimal("667000") and row.gp_pct == Decimal("25.01")
    assert row.cost_usd.quantize(Decimal("0.01")) == Decimal("2223.33")
    assert [line["item"] for line in row.cost_lines] == ["guide", "vehicle", "entrance", "meals", "hotels"]
    assert row.vehicle == "Van" and row.rate_rows[0] == "Tours!row 10 (T09)"
    assert row.reasons == []


def test_public_read_matches_the_engine_and_has_no_cost(db):
    result = _quote("T09", date(2027, 4, 12), 2, (7, 10))
    row = save_quote(db, result)
    public = get_public_quote(db, row.id)
    assert public == result.public
    dumped = public.model_dump()
    assert not [k for k in dumped if any(w in k for w in ("cost", "margin", "gp", "rate", "vehicle"))]


def test_usd_hotel_quote_round_trips(db):
    result = _quote("T13", date(2027, 5, 10), 2)
    row = save_quote(db, result)
    db.expire_all()
    hotels = next(line for line in db.get(Quote, row.id).cost_lines if line["item"] == "hotels")
    assert (hotels["lkr"], hotels["usd"]) == ("44000", "500")
    assert get_public_quote(db, row.id).price_usd == 2445


def test_refusal_is_saved_without_a_price(db):
    result = _quote("T12", date(2027, 4, 10), 1)
    row = save_quote(db, result, trace_id="trace-s04")
    assert row.status == "needs_specialist" and row.price_usd is None and row.cost_usd is None
    assert row.reasons[0]["code"] == "missing_rate"
    assert get_public_quote(db, row.id) is None


def test_unknown_quote_id_reads_as_none(db):
    assert get_public_quote(db, uuid.uuid4()) is None


def test_no_price_enquiry_takes_flags_and_trace_from_the_quote(db, conversation):
    row = save_quote(db, _quote("T11", date(2027, 1, 20), 2), conversation_id=conversation.id,
                     trace_id="trace-s05")
    enq = create_enquiry(db, "no_price", quote=row, notes="Traveller asked for Mirissa in January")
    db.expire_all()
    enq = db.get(Enquiry, enq.id)
    assert enq.flags == ["expired_rate"]                 # 6 nights, one flag
    assert (enq.quote_id, enq.conversation_id, enq.trace_id) == (row.id, conversation.id, "trace-s05")
    assert enq.status == "new" and enq.kind == "no_price"


def test_quote_enquiry_with_contact(db):
    row = save_quote(db, _quote("T01", date(2027, 1, 10), 2), trace_id="trace-s02")
    enq = create_enquiry(db, "quote", quote=row, contact={"name": "Test Traveller", "email": "t@test.example"})
    assert enq.flags == [] and enq.contact["name"] == "Test Traveller" and enq.trace_id == "trace-s02"


def test_custom_enquiry_without_quote(db, conversation):
    enq = create_enquiry(db, "custom", conversation_id=conversation.id, flags=["custom_itinerary"],
                         notes="10 days, tea country and beaches")
    assert enq.quote_id is None and enq.flags == ["custom_itinerary"]


def test_unknown_enquiry_kind_rejected(db):
    with pytest.raises(ValueError):
        create_enquiry(db, "complaint")


def test_visitor_last_quote(db, conversation):
    row = save_quote(db, _quote("T01", date(2027, 1, 10), 2))
    visitor = conversation.visitor
    visitor.last_quote_id = row.id
    db.flush()
    db.expire_all()
    assert db.scalar(select(Visitor.last_quote_id).where(Visitor.id == visitor.id)) == row.id
