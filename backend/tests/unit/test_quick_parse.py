"""Gemini fully down: the rule-based reading keeps the quote journeys working (Phase 12)."""

from __future__ import annotations

from datetime import date

import pytest

from app.graph.build import build_graph
from app.graph.nodes import Deps
from app.graph.quick_parse import find_date, find_party, find_tour, quick_analysis
from tests.unit.test_graph import TODAY, FakeModel, make, turn


@pytest.fixture(scope="module")
def base():
    return Deps.default(today=TODAY)


def down():
    """Every structured call fails, like a Gemini outage."""
    return FakeModel()


# ---- the parser -------------------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("2 adults on 10 January 2027", date(2027, 1, 10)),
    ("starting 3 May 2027.", date(2027, 5, 3)),
    ("from 20 January 2027, how much?", date(2027, 1, 20)),
    ("on January 10th, 2027", date(2027, 1, 10)),
    ("from 2027-04-12", date(2027, 4, 12)),
    ("on 15 March", date(2027, 3, 15)),           # no year: the next 15 March after today
    ("next spring", None),
])
def test_dates(text, expected):
    assert find_date(text, TODAY) == expected


@pytest.mark.parametrize("text,expected", [
    ("for 2 adults", (2, [], False)),
    ("We're 2 adults and 2 kids aged 7 and 10.", (2, [7, 10], False)),
    ("Actually there will be 4 adults", (4, [], False)),
    ("I'm travelling solo.", (1, [], False)),
    ("for two adults", (2, [], False)),
    ("2 adults and our 1-year-old baby", (2, [1], False)),
    ("2 adults and a child", (2, [], True)),       # a child without an age: Mira asks
    ("just me and my two kids aged 5 and 8", (1, [5, 8], False)),
])
def test_party(text, expected):
    assert find_party(text) == expected


@pytest.mark.parametrize("text,tour", [
    ("the Sigiriya and Minneriya day tour from Kandy", "T01"),
    ("the Cultural Triangle package", "T09"),
    ("Treasures of Sri Lanka", "T12"),
    ("The Mirissa beach stay", "T11"),
    ("Whale watching in Mirissa", "T05"),
    ("price for T08 please", "T08"),
    ("Is Yala open in September?", None),
])
def test_tours(base, text, tour):
    name = find_tour(text, base.tours)
    assert (next(t.tour_id for t in base.tours if t.name == name) if name else None) == tour


def test_nothing_to_go_on_keeps_the_handoff(base):
    assert quick_analysis("Tell me something nice", base.tours, TODAY) is None


# ---- whole journeys with Gemini down ------------------------------------------------------

def test_s02_quote_with_gemini_down(base):
    out = turn(make(base, down()), "How much is the Sigiriya and Minneriya day tour from Kandy for "
                                   "2 adults on 10 January 2027?")
    assert out["quote"]["price_usd"] == 315 and "llm_unavailable" in out["flags"]
    assert "USD 315" in out["response"]


def test_s03_two_turns_with_gemini_down(base):
    g = make(base, down())
    first = turn(g, "We're 2 adults and 2 kids aged 7 and 10.")
    assert first["party"] == {"adults": 2, "child_ages": [7, 10]} and first["action"] != "handoff"
    second = turn(g, "We'd like the Cultural Triangle package starting 12 April 2027. What's the price?")
    q = second["quote"]
    assert (q["price_usd"], q["deposit_usd"]) == (2965, 742)


def test_s13_update_party_with_gemini_down(base):
    g = make(base, down())
    turn(g, "Price for the Cultural Triangle package for 2 adults, starting 3 May 2027.")
    out = turn(g, "Actually there will be 4 adults, can you update the price?")
    assert (out["quote"]["price_usd"], out["quote"]["deposit_usd"]) == (3640, 910)


def test_s15_infant_with_gemini_down(base):
    out = turn(make(base, down()), "Whale watching in Mirissa on 15 March 2027 for 2 adults and our "
                                   "1-year-old baby. Price?")
    assert out["quote"]["price_usd"] == 275


def test_s04_still_no_price_with_gemini_down(base):
    out = turn(make(base, down()), "I'm travelling solo. Price for Treasures of Sri Lanka starting 10 April 2027?")
    assert out["quote"] is None and "no_price" in out["flags"]


def test_unreadable_message_is_still_a_safe_handoff(base):
    out = turn(make(base, down()), "Hmm, what would you recommend for us?")
    assert out["action"] == "handoff" and out["quote"] is None


def test_gemini_working_never_uses_the_rules(base):
    from app.llm.schemas import Intent, TripDetails, TurnAnalysis
    ok = FakeModel(TurnAnalysis=[TurnAnalysis(intent=Intent.GREETING, needs_retrieval=False, trip=TripDetails())])
    out = turn(make(base, ok), "Hi")
    assert "llm_unavailable" not in out["flags"]


def test_build_graph_is_importable():
    assert callable(build_graph)


@pytest.mark.parametrize("text,days", [("about 10 days", 10), ("6 nights", 7), ("about a week", 7),
                                       ("two weeks", 14), ("a fortnight", 14), ("soon", None)])
def test_days(text, days):
    from app.graph.quick_parse import find_days
    assert find_days(text) == days


def test_planner_with_gemini_down_suggests_tours(base):
    out = turn(make(base, down()), "We'd like about 10 days of beaches and wildlife, 2 adults, from 5 March "
                                   "2027. What do you suggest?")
    assert out["action"] == "match_tours" and len(out["tour_cards"]) == 3
    assert out["duration_days"] == 10 and {"beaches", "wildlife"} <= set(out["interests"])
    assert any(c["type"] == "specialist_notice" and c["reason"] == "custom_plan" for c in out["ui"])


def test_s13_first_turn_with_gemini_down(base):
    out = turn(make(base, down()), "We want to see the ancient cities, about a week.")
    assert out["action"] == "match_tours" and out["tour_cards"][0]["tour_id"] == "T09"
