"""Step 14.2: each evaluation assertion catches what it should and passes what it should."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

EVAL_DIR = Path(os.environ.get("MIRA_EVAL_DIR") or Path(__file__).resolve().parents[3] / "evaluation")
sys.path.insert(0, str(EVAL_DIR.parent))

A = pytest.importorskip("evaluation.assertions")
from evaluation.assertions import CaseRun, TurnResult, amounts, check_case  # noqa: E402

PUBLISHED = {"P01", "P02", "T01", "T09"}
S02_QUOTE = {"status": "ok", "tour_id": "T01", "price_usd": 315, "deposit_usd": 315, "balance_usd": 0,
             "cost_usd": 220.0, "reasons": []}
S02_ENGINE = {"status": "ok", "price_usd": 315, "deposit_usd": 315}
QUOTE_EXP = {"type": "quote", "tour": "T01", "price_usd": 315, "deposit_usd": 315}
FLAG_EXP = {"type": "flag_no_price", "reason": "missing_rate"}


def turn(**kw) -> TurnResult:
    kw.setdefault("message", "hi")
    return TurnResult(**kw)


def priced(**kw) -> TurnResult:
    return turn(quote=dict(S02_QUOTE), recomputed=dict(S02_ENGINE),
                response=kw.pop("response", "USD 315 in total, deposit USD 315."), **kw)


def run(*turns, published=PUBLISHED) -> CaseRun:
    return CaseRun(case_id="X", turns=list(turns), published=set(published))


def result(r: CaseRun, name: str, expected=None, retrieval=None):
    checks = {c.name: c for c in check_case(r, expected or {"type": "behaviour"}, retrieval)}
    return checks.get(name)


# ---- amounts ----------------------------------------------------------------------------------

@pytest.mark.parametrize("text,found", [
    ("USD 2,965 in total", [2965]), ("$742 deposit", [742]), ("LKR 667,000", [667000]),
    ("US$315 and 315 USD", [315, 315]), ("about 300 dollars", [300]), ("Rs. 500", [500]),
    ("50% refund, 7 days, 2027", []), ("aged 7 and 10", []),
])
def test_amounts(text, found):
    assert amounts(text) == found


# ---- price_exact / price_reverified -----------------------------------------------------------

def test_price_exact_passes_and_fails():
    assert result(run(priced()), "price_exact", QUOTE_EXP).passed
    wrong = priced()
    wrong.quote["price_usd"] = 320
    assert not result(run(wrong), "price_exact", QUOTE_EXP).passed
    assert not result(run(turn(response="A specialist will confirm.")), "price_exact", QUOTE_EXP).passed


def test_price_exact_sequence_in_order():
    exp = {"type": "quote_sequence", "quotes": [{"tour": "T01", "price_usd": 315, "deposit_usd": 315},
                                                {"tour": "T01", "price_usd": 400, "deposit_usd": 400}]}
    second = priced(response="USD 400")
    second.quote.update(price_usd=400, deposit_usd=400)
    assert result(run(turn(), priced(), second), "price_exact", exp).passed
    assert not result(run(second, priced()), "price_exact", exp).passed        # wrong order
    assert not result(run(priced()), "price_exact", exp).passed                 # second quote missing


def test_price_reverified_catches_a_stored_price_the_engine_disagrees_with():
    t = priced()
    t.recomputed["price_usd"] = 310
    assert not result(run(t), "price_reverified").passed
    assert result(run(priced()), "price_reverified").passed
    assert result(run(turn()), "price_reverified") is None                     # nothing priced


# ---- invented amounts ------------------------------------------------------------------------------

def test_amount_not_in_the_quote_is_invented():
    assert result(run(priced()), "no_invented_amount").passed
    assert not result(run(priced(response="USD 315, or USD 280 with a discount.")), "no_invented_amount").passed


def test_any_amount_in_a_flag_case_is_invented():
    assert not result(run(turn(response="Probably around USD 900.")), "no_invented_amount").passed
    assert result(run(turn(response="A specialist will confirm the price.")), "no_invented_amount").passed


def test_amount_hidden_in_a_ui_component_is_caught():
    t = turn(response="Here are some tours.", ui=[{"type": "tour_card", "why": "Only $199 this week"}])
    assert not result(run(t), "no_invented_amount").passed


def test_an_earlier_quote_may_be_mentioned_again():
    later = turn(response="Your earlier price was USD 315.")
    assert result(run(priced(), later), "no_invented_amount").passed


# ---- flags -----------------------------------------------------------------------------------------

def test_flag_case_must_not_be_priced_and_must_save_the_flag():
    ok = turn(response="A specialist will confirm.", enquiry={"kind": "no_price", "flags": ["no_price", "missing_rate"]})
    assert result(run(ok), "no_price_when_flagged", FLAG_EXP).passed
    assert result(run(ok), "flag_saved", FLAG_EXP).passed
    assert not result(run(priced()), "no_price_when_flagged", FLAG_EXP).passed
    card = turn(ui=[{"type": "price_breakdown", "quote_id": "q"}])
    assert not result(run(card), "no_price_when_flagged", FLAG_EXP).passed
    wrong_reason = turn(enquiry={"kind": "no_price", "flags": ["no_price", "expired_rate"]})
    assert not result(run(wrong_reason), "flag_saved", FLAG_EXP).passed
    assert not result(run(turn()), "flag_saved", FLAG_EXP).passed              # nothing saved


def test_flag_checks_do_not_apply_to_quote_cases():
    assert result(run(priced()), "flag_saved", QUOTE_EXP) is None


def test_custom_enquiry():
    exp = {"type": "custom_enquiry"}
    ok = turn(enquiry={"kind": "custom", "flags": ["handoff_requested"]},
              ui=[{"type": "specialist_notice", "reason": "custom_plan"}])
    assert result(run(turn(), ok), "custom_enquiry", exp).passed
    assert not result(run(turn(), turn()), "custom_enquiry", exp).passed


# ---- UI, retrieval, leaks, questions, errors ---------------------------------------------------------

def test_ui_invalid_or_dropped_fails():
    assert result(run(turn(ui=[{"type": "tour_card"}])), "ui_valid").passed
    assert not result(run(turn(ui_invalid=["tour_card: ValidationError"])), "ui_valid").passed
    assert not result(run(turn(ui_rejected=[{"type": "price_breakdown", "reason": "no quote"}])), "ui_valid").passed


def test_draft_retrieved_fails():
    assert result(run(turn(retrieved=["P01"], cited=["P01"])), "no_draft_retrieved").passed
    assert not result(run(turn(retrieved=["P01", "DRAFT9"])), "no_draft_retrieved").passed
    assert result(run(turn()), "no_draft_retrieved") is None


def test_grounding_rules():
    must = {"abstain": False, "must_cite": ["P02"], "must_not_cite": ["P06"]}
    assert result(run(turn(retrieved=["P02"], cited=["P02"])), "grounding", retrieval=must).passed
    assert not result(run(turn(retrieved=["P02"], cited=[])), "grounding", retrieval=must).passed     # not cited
    assert not result(run(turn(retrieved=[], cited=[])), "grounding", retrieval=must).passed          # not found
    assert not result(run(turn(retrieved=["P02", "P06"], cited=["P02", "P06"])), "grounding", retrieval=must).passed
    abstain = {"abstain": True, "must_cite": [], "must_not_cite": []}
    assert result(run(turn()), "grounding", retrieval=abstain).passed
    assert not result(run(turn(cited=["P01"])), "grounding", retrieval=abstain).passed
    assert result(run(turn()), "grounding") is None


def test_cost_leaks_are_caught():
    assert result(run(priced()), "no_cost_leak").passed
    assert not result(run(priced(response="USD 315; our gross profit is 30%.")), "no_cost_leak").passed
    assert not result(run(priced(ui=[{"type": "x", "cost_usd": 220}])), "no_cost_leak").passed
    assert not result(run(priced(response="USD 315 (it costs us USD 220).")), "no_cost_leak").passed
    assert result(run(turn(response="The tour costs USD 0? no.")), "no_cost_leak").passed     # the word alone is fine


def test_question_limit():
    assert result(run(turn(questions_asked=3)), "questions_le_3").passed
    assert not result(run(turn(questions_asked=1), turn(questions_asked=4)), "questions_le_3").passed


def test_error_turn_fails():
    assert not result(run(turn(error="chat turn failed")), "no_error").passed


# ---- the case files ----------------------------------------------------------------------------------

def test_cases_load_with_requirements_and_enough_multi_turn():
    from evaluation.cases import load_cases
    cases = load_cases()
    assert len([c for c in cases if c.source == "starter"]) == 17
    assert all(c.requirement for c in cases)
    multi = [c.id for c in cases if c.multi_turn]
    assert len(multi) >= 5 and {"S03", "S13", "C-M01"} <= set(multi)
    assert {c.kind for c in cases} <= {"quote", "quote_sequence", "flag_no_price", "behaviour", "custom_enquiry"}
