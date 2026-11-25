"""Phase 16 regression: an older page's exact title or stated length must not be priced as a
different current tour (baseline eval case C-R05).

"Cultural Triangle Tour" (T16, an older 5-night page with no rate row) and "Cultural Triangle
Sri Lanka Package" (T09, priced) reduce to the same title words, so T09 used to win the tie and
Mira quoted USD 2,125 for a tour the traveller didn't ask about.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.graph.nodes import Deps
from app.graph.tours import match_tour, stated_days
from tests.unit.test_graph import FakeModel, R, T, make, turn

TODAY = date(2026, 11, 19)


@pytest.fixture(scope="module")
def base():
    return Deps.default(today=TODAY)


@pytest.mark.parametrize("text,days", [
    ("5-night Cultural Triangle Tour", 6), ("the 5 nights tour", 6), ("a 6-day trip", 6),
    ("seven nights", 8), ("Cultural Triangle package", None), ("for 2 adults", None),
])
def test_stated_days(text, days):
    assert stated_days(text) == days


@pytest.mark.parametrize("mention,tour", [
    ("5-night Cultural Triangle Tour", "T16"),        # the length says which page
    ("the 5-night Cultural Triangle Tour", "T16"),
    ("Cultural Triangle Tour", "T16"),                # T16's exact title
    ("6-night Cultural Triangle", "T09"),             # the length says the current package
    ("Cultural Triangle package", "T09"),             # S03
    ("Cultural Triangle Sri Lanka Package", "T09"),
    ("Treasures of Sri Lanka", "T12"),
    ("Sigiriya and Minneriya day tour from Kandy", "T01"),
])
def test_match_tour_uses_title_and_length(base, mention, tour):
    assert match_tour(mention, base.tours) == tour


def test_length_in_the_message_decides_when_the_mention_drops_it(base):
    assert match_tour("Cultural Triangle", base.tours, "the 5-night Cultural Triangle trip please") == "T16"
    assert match_tour("Cultural Triangle", base.tours, "just the Cultural Triangle trip please") == "T09"


@pytest.mark.parametrize("mention", ["5-night Cultural Triangle Tour", "Cultural Triangle Tour", "Cultural Triangle"])
def test_c_r05_old_page_is_not_priced_as_the_new_package(base, mention):
    """The whole turn: the old page has no rate row, so no price and a staff flag."""
    model = FakeModel(RouterDecision=[R("quote", mention)],
                      TripDetails=[T(tour_mention=mention,
                                     start_date=date(2027, 5, 3), adults=2)])
    out = turn(make(base, model), "How much is the 5-night Cultural Triangle Tour for 2 adults from 3 May 2027?")
    assert out["quote"] is None or out["quote"].get("tour_id") != "T09"
    assert "USD 2,125" not in out["response"]
    assert "no_price" in out["flags"]


# Eval S15: "Whale watching in Mirissa ... Price?" -- the LLM files "whale watching" as an
# interest, so no tour was named and Mira listed options instead of pricing T05.
@pytest.mark.parametrize("interests,places,tour", [
    (["whale watching"], ["Mirissa"], "T05"),
    (["whale watching"], [], "T05"),
    (["wildlife"], [], None),                    # one word is too loose to name a tour
    (["ancient cities"], [], None),              # no title has both words
    (["culture", "wildlife"], [], None),
])
def test_product_match(base, interests, places, tour):
    from app.graph.tours import product_match
    assert product_match(interests, places, base.tours) == tour


@pytest.mark.parametrize("text,child", [
    ("2 adults, starting 3 May 2027.", False), ("We want to see the ancient cities", False),
    ("2 adults and our 1-year-old baby", True), ("with our two kids", True),
    ("my daughter is 8", True), ("a 10 year old", True),
])
def test_mentions_child(text, child):
    from langchain_core.messages import HumanMessage
    from app.graph.nodes import _mentions_child
    assert _mentions_child({"messages": [HumanMessage(content=text)]}) is child
