"""Step 4.6: our own eval cases (evaluation/test_cases/custom.jsonl) agree with the engine.

Every pricing or rate case carries the structured booking its conversation describes, so the
expected numbers are checked here without an LLM. If the engine or a case drifts, this fails.
"""

import json
import os
from datetime import date
from pathlib import Path

import pytest

from app.pricing import QuoteRequest, calculate_quote

TODAY = date(2026, 11, 19)
EVAL_DIR = Path(os.environ.get("MIRA_EVAL_DIR") or Path(__file__).resolve().parents[3] / "evaluation")
CUSTOM = EVAL_DIR / "test_cases" / "custom.jsonl"


def load_cases() -> list[dict]:
    return [json.loads(line) for line in CUSTOM.read_text(encoding="utf-8").splitlines() if line.strip()]


CASES = load_cases() if CUSTOM.exists() else []
PRICED = [c for c in CASES if "pricing_input" in c]


def test_custom_cases_exist():
    assert CUSTOM.exists(), f"missing {CUSTOM}"
    assert len(CASES) >= 14


def test_ids_are_unique_and_do_not_clash_with_the_starters(dataset):
    ids = [c["id"] for c in CASES]
    assert len(ids) == len(set(ids))
    assert not set(ids) & {c.id for c in dataset.eval_seed}


def test_case_shape():
    for c in CASES:
        assert set(c) >= {"id", "category", "requirement", "turns", "expected"}, c["id"]
        assert c["turns"] and all(isinstance(t, str) and t for t in c["turns"]), c["id"]
        assert c["expected"]["type"] in {"quote", "quote_sequence", "flag_no_price", "behaviour"}, c["id"]


def test_requirement_counts():
    """Plan §8.1: R5 ~9 and R6 ~8 including the starters (S02, S03, S15 / S04, S05, S06, S11)."""
    by_req = {r: sum(c["requirement"] == r for c in CASES) for r in ("R5", "R6")}
    assert by_req["R5"] + 3 >= 9 and by_req["R6"] + 4 >= 8


def _quote(inp: dict):
    req = QuoteRequest(tour_id=inp["tour_id"], start_date=date.fromisoformat(inp["start_date"]),
                       adults=inp["adults"], child_ages=tuple(inp["child_ages"]))
    return calculate_quote(req, today=TODAY)


@pytest.mark.parametrize("case", PRICED, ids=[c["id"] for c in PRICED])
def test_expected_numbers_match_the_engine(case):
    exp = case["expected"]
    if exp["type"] == "flag_no_price":
        r = _quote(case["pricing_input"])
        assert r.status == "needs_specialist"
        assert exp["reason"] in {x.code.value for x in r.reasons}
        return
    inputs = case["pricing_input"] if isinstance(case["pricing_input"], list) else [case["pricing_input"]]
    quotes = exp["quotes"] if exp["type"] == "quote_sequence" else [exp]
    assert len(inputs) == len(quotes)
    for inp, q in zip(inputs, quotes):
        r = _quote(inp)
        assert r.status == "ok", r.reasons
        assert (r.public.tour_id, r.public.price_usd, r.public.deposit_usd) == \
               (q["tour"], q["price_usd"], q["deposit_usd"])


def test_starter_quotes_also_match_the_engine(dataset):
    """S02, S03, S15 and both S13 quotes, using the bookings their conversations describe."""
    bookings = {"S02": [("T01", "2027-01-10", 2, ())], "S03": [("T09", "2027-04-12", 2, (7, 10))],
                "S15": [("T05", "2027-03-15", 2, (1,))],
                "S13": [("T09", "2027-05-03", 2, ()), ("T09", "2027-05-03", 4, ())]}
    seeds = {c.id: c for c in dataset.eval_seed}
    for sid, inputs in bookings.items():
        exp = seeds[sid].expected
        quotes = exp["quotes"] if exp["type"] == "quote_sequence" else [exp]
        for (t, s, a, ages), q in zip(inputs, quotes, strict=True):
            r = _quote(dict(tour_id=t, start_date=s, adults=a, child_ages=ages))
            assert (r.public.price_usd, r.public.deposit_usd) == (q["price_usd"], q["deposit_usd"]), sid


# R4 grounding cases (step 6.14): the retriever finds the sources each case needs ---------------

GROUNDED = [c for c in CASES if "retrieval" in c]


def test_r4_case_count():
    """Plan §8.1: ~10 R4 cases including the 6 starters (S07-S10, S16, S17)."""
    assert len(GROUNDED) + 6 >= 10 and all(c["requirement"] == "R4" for c in GROUNDED)


@pytest.mark.parametrize("case", GROUNDED, ids=[c["id"] for c in GROUNDED])
def test_r4_retrieval_expectations(case):
    from app.core.config import get_settings
    if get_settings().gemini_api_key is None:
        pytest.skip("needs GEMINI_API_KEY")
    from app.rag import get_retriever
    exp = case["retrieval"]
    r = get_retriever().retrieve(case["turns"][-1])
    found = [c.doc_id for c in r.chunks]
    assert r.abstain is exp["abstain"], (r.reason, found)
    assert set(exp["must_cite"]) <= set(found), found
    assert not set(exp["must_not_cite"]) & set(found), found
