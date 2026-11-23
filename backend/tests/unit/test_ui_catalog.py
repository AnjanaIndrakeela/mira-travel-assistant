"""Phase 11: the UI catalog, the validator and code-chosen components (11.2-11.4, 11.13, 11.15)."""

from __future__ import annotations

import json
import uuid

import pytest
from pydantic import ValidationError

from app.data_loader import get_dataset
from app.guards.ui_validator import validate_ui
from app.ui.build import accent_for, choose_components, itinerary_days, tour_card
from app.ui.catalog import ADAPTER, COMPONENT_TYPES, PriceBreakdown, json_schema
from app.ui.export import DEFAULT, render

QID = str(uuid.uuid4())
SRC = {"doc_id": "T01", "title": "Sigiriya and Minneriya day tour"}


@pytest.fixture(scope="module")
def ds():
    return get_dataset()


def card(**over):
    base = {"type": "tour_card", "tour_id": "T01", "title": "Sigiriya and Minneriya day tour",
            "duration": "1 day", "accent": "teal", "bookable": True, "source": SRC}
    return {**base, **over}


# ---- 11.2 / 11.3 catalog ----------------------------------------------------------------

def test_catalog_has_the_eight_components():
    assert set(COMPONENT_TYPES) == {"traveller_picker", "tour_card", "itinerary_day", "price_breakdown",
                                    "booking_form", "specialist_notice", "source_list", "welcome_back"}
    names = {s["properties"]["type"]["const"] for s in json_schema()["$defs"].values() if "type" in s.get("properties", {})}
    assert names == set(COMPONENT_TYPES)


def test_price_breakdown_has_no_price_field():
    assert set(PriceBreakdown.model_fields) == {"type", "quote_id"}
    with pytest.raises(ValidationError):
        ADAPTER.validate_python({"type": "price_breakdown", "quote_id": QID, "price_usd": 1})


def test_unknown_type_is_a_validation_error():
    with pytest.raises(ValidationError):
        ADAPTER.validate_python({"type": "script", "src": "x"})


def test_exported_schema_matches_the_catalog():
    """frontend/src/lib/catalog.schema.json is the contract the Zod schemas are checked against."""
    path = DEFAULT
    if not path.exists():
        pytest.skip("frontend/src/lib is not mounted in this container")
    assert json.loads(path.read_text(encoding="utf-8")) == json.loads(render()), "run: python -m app.ui.export"


# ---- 11.4 validator ---------------------------------------------------------------------

def test_unknown_type_is_dropped_and_reported():
    ui, rejected = validate_ui([{"type": "iframe", "src": "https://evil.example"}, card()], quote_id=None)
    assert [c["type"] for c in ui] == ["tour_card"]
    assert rejected == [{"type": "unknown", "reason": "unknown_type"}]


def test_bad_props_are_dropped():
    ui, rejected = validate_ui([card(accent="neon"), card(tour_id="T1"), card(extra="x"),
                                {"type": "traveller_picker", "adults": 0}], quote_id=None)
    assert ui == [] and {r["reason"] for r in rejected} == {"invalid_props"} and len(rejected) == 4


def test_price_component_without_the_saved_quote_is_dropped():
    other = str(uuid.uuid4())
    ui, rejected = validate_ui([{"type": "price_breakdown", "quote_id": other},
                                {"type": "booking_form", "quote_id": other},
                                {"type": "price_breakdown", "quote_id": QID}], quote_id=QID)
    assert ui == [{"type": "price_breakdown", "quote_id": QID}]
    assert [r["reason"] for r in rejected] == ["no_saved_quote", "no_saved_quote"]
    ui, rejected = validate_ui([{"type": "price_breakdown", "quote_id": QID}], quote_id=None)
    assert ui == [] and rejected[0]["reason"] == "no_saved_quote"


# ---- 11.15 malicious payloads -----------------------------------------------------------

@pytest.mark.parametrize("payload", [
    {"type": "script", "code": "alert(1)"},
    {"type": "tour_card", "__proto__": {}},
    card(title="<script>alert(1)</script>"),
    card(title="<img src=x onerror=alert(1)>"),
    card(highlights=["click javascript:alert(1)"]),
    card(why="Only USD 9 today"),                                  # forged price in text
    card(highlights=["Now $1 per person"]),
    {"type": "specialist_notice", "reason": "no_price", "message": "Pay 200 USD to book"},
    {"type": "price_breakdown", "quote_id": QID, "price_usd": 1, "deposit_usd": 1},
    {"type": "booking_form", "quote_id": QID, "fields": ["name", "password"]},
    {"type": "source_list", "items": [{"n": 1, "doc_id": "javascript:x", "title": "t", "section": "s"}]},
    "not even an object",
])
def test_malicious_payloads_are_all_rejected(payload):
    ui, rejected = validate_ui([payload], quote_id=QID)
    assert ui == [] and len(rejected) == 1


def test_rejections_never_copy_prop_values():
    _, rejected = validate_ui([card(title="<script>steal('a@b.com')</script>")], quote_id=None)
    assert "a@b.com" not in str(rejected) and "script" not in str(rejected)


# ---- 11.13 build_ui chooses components from verified state -------------------------------

def test_quote_gives_card_price_and_booking_form(ds):
    state = {"action": "price", "quote": {"tour_id": "T01"}, "quote_id": QID}
    ui, rejected = validate_ui(choose_components(state, content=ds.content, rates=ds.rates), quote_id=QID)
    assert [c["type"] for c in ui] == ["tour_card", "price_breakdown", "booking_form"] and not rejected
    assert ui[0]["bookable"] and ui[0]["highlights"]


def test_no_price_gives_specialist_notice_only(ds):
    state = {"action": "price", "refusals": [{"code": "missing_rate", "message": "A travel specialist "
                                              "will confirm the price for this tour."}],
             "enquiry_id": str(uuid.uuid4())}
    ui, _ = validate_ui(choose_components(state, content=ds.content, rates=ds.rates), quote_id=None)
    assert [c["type"] for c in ui] == ["specialist_notice"]
    assert ui[0]["reason"] == "no_price" and ui[0]["enquiry_id"] == state["enquiry_id"]


def test_planner_gets_tour_cards_and_the_top_itinerary(ds):
    cards = [{"tour_id": t, "why": "fits"} for t in ("T09", "T13", "T08")]
    state = {"action": "match_tours", "tour_cards": cards}
    ui, rejected = validate_ui(choose_components(state, content=ds.content, rates=ds.rates), quote_id=None)
    assert not rejected
    assert [c["tour_id"] for c in ui if c["type"] == "tour_card"] == ["T09", "T13", "T08"]
    days = [c for c in ui if c["type"] == "itinerary_day"]
    assert days and {d["tour_id"] for d in days} == {"T09"} and [d["day"] for d in days] == list(range(1, 8))


def test_custom_request_and_unanswered_question(ds):
    ui = choose_components({"action": "match_tours", "unmatched_tour": "Jaffna"}, content=ds.content, rates=ds.rates)
    assert ui[0]["type"] == "specialist_notice" and ui[0]["reason"] == "custom_request"
    ui = choose_components({"action": "retrieve", "abstain_reason": "no_match"}, content=ds.content, rates=ds.rates)
    assert ui[0]["reason"] == "unanswered_question"


def test_asking_who_travels_shows_the_traveller_picker(ds):
    state = {"action": "ask", "question": "Could you tell me who is travelling?", "missing": ["adults"]}
    ui, _ = validate_ui(choose_components(state, content=ds.content, rates=ds.rates), quote_id=None)
    assert ui == [{"type": "traveller_picker", "adults": 2, "child_ages": [], "ask_child_ages": False}]
    state = {"action": "ask", "question": "Could you tell me the start date?", "missing": ["start_date"]}
    assert choose_components(state, content=ds.content, rates=ds.rates) == []


def test_tour_question_shows_its_itinerary(ds):
    state = {"action": "retrieve", "intent": "tour_info", "selected_tour_id": "T08"}
    ui, _ = validate_ui(choose_components(state, content=ds.content, rates=ds.rates), quote_id=None)
    assert ui[0]["type"] == "tour_card" and sum(c["type"] == "itinerary_day" for c in ui) == 8


def test_cards_and_days_never_carry_money(ds):
    for doc in ds.content.by_type("tour"):
        c = tour_card(doc.id, content=ds.content, rates=ds.rates)
        days = itinerary_days(doc.id, content=ds.content)
        ui, rejected = validate_ui(([c] if c else []) + days, quote_id=None)
        assert not rejected, (doc.id, rejected)


def test_draft_tour_never_becomes_a_card(ds):
    assert tour_card("T15", content=ds.content, rates=ds.rates) is None


def test_one_accent_per_tour():
    assert accent_for("T01") == accent_for("T01") and accent_for("T01") != accent_for("T02")
