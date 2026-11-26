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
from app.ui.export import A2UI_DEFAULT, DEFAULT, a2ui_catalog, render, render_a2ui

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

def test_catalog_has_the_ten_components():
    assert set(COMPONENT_TYPES) == {"traveller_picker", "tour_card", "itinerary_day", "price_breakdown",
                                    "booking_form", "specialist_notice", "source_list", "welcome_back",
                                    "photo_gallery", "trip_plan"}
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


def test_a2ui_catalog_has_every_component_from_the_pydantic_models():
    """The A2UI custom catalog is generated from the same models: same components, same props."""
    cat = a2ui_catalog()
    assert cat["catalogId"] == "https://ceylon-compass.example/catalog/v1"
    assert {c["x-mira-type"] for c in cat["components"].values() if "x-mira-type" in c} == set(COMPONENT_TYPES)
    assert cat["components"]["MiraReply"]["required"] == ["id", "component", "children"]
    card = cat["components"]["TourCard"]
    assert card["properties"]["component"] == {"const": "TourCard"} and "type" not in card["properties"]
    assert {"id", "component", "tour_id", "source"} <= set(card["required"])
    assert card["additionalProperties"] is False                     # no extra props, as in Pydantic
    refs = json.dumps(cat["components"])
    assert all(f"#/$defs/{name}" in refs for name in cat["$defs"])   # every shared type is used


def test_exported_a2ui_catalog_is_up_to_date():
    path = A2UI_DEFAULT
    if not path.exists():
        pytest.skip("frontend/src/lib is not mounted in this container")
    assert json.loads(path.read_text(encoding="utf-8")) == json.loads(render_a2ui()), "run: python -m app.ui.export"


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
    state = {"action": "retrieve", "intent": "tour_info", "selected_tour_id": "T08",
             "tour_mention": "Highlights of Sri Lanka"}
    ui, _ = validate_ui(choose_components(state, content=ds.content, rates=ds.rates), quote_id=None)
    assert ui[0]["type"] == "tour_card" and sum(c["type"] == "itinerary_day" for c in ui) == 8


def test_remembered_tour_is_not_shown_for_another_question(ds):
    """Asked about Kandy Heritage Stay, then "Is Yala open in September?": no T07 card, and the
    unanswered question gets the specialist notice instead."""
    state = {"action": "retrieve", "intent": "tour_info", "selected_tour_id": "T07", "tour_mention": None}
    assert choose_components(state, content=ds.content, rates=ds.rates) == []
    state = {**state, "tour_mention": "Kandy Heritage Stay", "abstain_reason": "not_in_sources"}
    types = [c["type"] for c in choose_components(state, content=ds.content, rates=ds.rates)]
    assert types == ["specialist_notice"]


def test_cards_and_days_never_carry_money(ds):
    for doc in ds.content.by_type("tour"):
        c = tour_card(doc.id, content=ds.content, rates=ds.rates)
        days = itinerary_days(doc.id, content=ds.content)
        ui, rejected = validate_ui(([c] if c else []) + days, quote_id=None)
        assert not rejected, (doc.id, rejected)


def test_tour_cards_show_where_the_tour_stays(ds):
    def hotels(tid):
        return tour_card(tid, content=ds.content, rates=ds.rates)["hotels"]
    # day-by-day stays, with their nights
    assert hotels("T09") == ["Anuradhapura Heritage Lodge or similar (2 nights)", "Sigiriya Village or similar (2 nights)",
                             "Hotel Suisse, Hotel Topaz or similar (2 nights)"]
    # the page's own "Route and hotels" list
    assert hotels("T12")[0] == "Negombo – Suriya Resort or similar" and len(hotels("T12")) == 9
    # the front-matter list when the page has nothing else
    assert hotels("T13") == ["Udawalawe Safari Camp", "Cinnamon Wild Yala"]
    assert hotels("T01") == []                                    # a day tour: no hotel


def test_draft_tour_never_becomes_a_card(ds):
    assert tour_card("T15", content=ds.content, rates=ds.rates) is None


def test_one_accent_per_tour():
    assert accent_for("T01") == accent_for("T01") and accent_for("T01") != accent_for("T02")


def test_planner_offers_a_custom_plan_with_a_summary(ds):
    state = {"action": "match_tours", "tour_cards": [{"tour_id": "T13", "why": "fits"}],
             "interests": ["beaches", "wildlife"], "duration_days": 10,
             "party": {"adults": 2, "child_ages": []}, "start_date": "2027-03-05"}
    ui, rejected = validate_ui(choose_components(state, content=ds.content, rates=ds.rates), quote_id=None)
    notice = next(c for c in ui if c["type"] == "specialist_notice")
    assert not rejected and notice["reason"] == "custom_plan"
    assert notice["summary"] == "Interests: beaches, wildlife. About 10 days. 2 adults. From 2027-03-05."
    assert not any(c["type"] in {"price_breakdown", "booking_form"} for c in ui)   # no price for a custom trip


def test_unmatched_tour_gets_one_notice_not_two(ds):
    state = {"action": "match_tours", "unmatched_tour": "Adam's Peak", "tour_cards": [{"tour_id": "T09", "why": "x"}]}
    ui = choose_components(state, content=ds.content, rates=ds.rates)
    assert [c["reason"] for c in ui if c["type"] == "specialist_notice"] == ["custom_request"]


# ---- A2UI messages (step 4) --------------------------------------------------------------

def test_a_reply_becomes_one_a2ui_surface_with_our_components_in_order():
    from app.ui.a2ui import from_component, to_a2ui
    from app.ui.export import CATALOG_ID
    content = get_dataset().content
    ui, _ = validate_ui([tour_card("T01", content=content, rates=get_dataset().rates),
                         {"type": "price_breakdown", "quote_id": QID},
                         {"type": "booking_form", "quote_id": QID, "fields": ["name", "email", "phone", "card"]}],
                        quote_id=QID)
    msgs = to_a2ui(ui, "reply-1")
    assert [list(m)[1] for m in msgs] == ["createSurface", "updateComponents"]
    assert all(m["version"] == "1.0" for m in msgs)
    assert msgs[0]["createSurface"] == {"surfaceId": "reply-1", "catalogId": CATALOG_ID}
    root, *parts = msgs[1]["updateComponents"]["components"]
    assert root == {"id": "root", "component": "MiraReply", "children": ["c1", "c2", "c3"]}
    assert [p["component"] for p in parts] == ["TourCard", "PriceBreakdown", "BookingForm"]
    assert all("type" not in p for p in parts)
    assert [from_component(p) for p in parts] == ui            # nothing lost or added on the way


def test_no_components_means_no_surface():
    from app.ui.a2ui import to_a2ui
    assert to_a2ui([], "reply-2") == []


def test_saved_cards_from_an_older_catalog_are_dropped_not_an_error():
    """Step 8: a saved chat may hold cards an older app version wrote."""
    from app.ui.a2ui import to_a2ui
    good = {"type": "specialist_notice", "reason": "handoff", "message": "A specialist will get back to you."}
    old = [{"type": "price_card", "price": 315}, {"no_type": True}, "text", {"type": "tour_card"}, good]
    out = to_a2ui(old, "saved-1")
    comps = out[1]["updateComponents"]["components"]
    assert [c["component"] for c in comps] == ["MiraReply", "SpecialistNotice"]
    assert to_a2ui(old[:4], "saved-2") == []


def test_a2ui_conversion_drops_a_component_that_fails_the_round_trip():
    from app.ui.a2ui import to_a2ui
    bad = {"type": "price_breakdown", "quote_id": "not-a-uuid"}       # would never pass validate_ui
    msgs = to_a2ui([bad, {"type": "price_breakdown", "quote_id": QID}], "reply-3")
    parts = msgs[1]["updateComponents"]["components"][1:]
    assert [p["id"] for p in parts] == ["c2"]
