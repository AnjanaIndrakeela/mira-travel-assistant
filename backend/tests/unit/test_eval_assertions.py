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


# ---- Phase 15: R7, booking, access, judge, coverage ------------------------------------------------

def test_every_quote_needs_an_enquiry_and_a_trace_when_tracing():
    t = priced(enquiry={"kind": "quote", "flags": [], "trace_id": "abc"})
    t.quote["trace_id"] = "abc"
    r = run(t)
    r.tracing = True
    assert result(r, "quote_saved_as_enquiry").passed
    t.enquiry["trace_id"] = None
    assert not result(r, "quote_saved_as_enquiry").passed
    r.tracing = False                                          # tracing off: the trace can't be required
    assert result(r, "quote_saved_as_enquiry").passed
    assert not result(run(priced()), "quote_saved_as_enquiry").passed       # no enquiry at all


def test_booking_result():
    from evaluation.assertions import booking_result
    ok = run(priced())
    ok.booking = {"status": "confirmed"}
    assert booking_result(ok, {"expect": "confirmed"}).passed
    failed = run(priced())
    failed.booking = {"status": "payment_failed", "enquiry_kind": "booking_failed", "next_steps": ["retry"]}
    assert booking_result(failed, {"expect": "payment_failed"}).passed
    failed.booking["enquiry_kind"] = None                       # failure must leave a way forward
    assert not booking_result(failed, {"expect": "payment_failed"}).passed
    assert booking_result(run(priced()), None) is None


def test_enquiry_private():
    from evaluation.assertions import enquiry_private
    r = run(priced())
    r.access = {"public": 405, "staff": 401}
    assert enquiry_private(r).passed
    r.access = {"public": 200, "staff": 401}
    assert not enquiry_private(r).passed


def test_judge_verdict_unavailable_is_not_counted():
    from evaluation.assertions import judge_verdict
    r = run(turn())
    r.judge = {"passed": None, "reason": "judge unavailable"}
    assert judge_verdict(r) is None
    r.judge = {"passed": False, "reason": "promised a free stay"}
    assert not judge_verdict(r).passed


def test_every_coverage_tag_has_a_case():
    from evaluation.cases import COVERAGE_TAGS, load_cases
    cases = load_cases()
    missing = [t for t in COVERAGE_TAGS if not any(t in c.all_tags for c in cases)]
    assert not missing, missing
    assert len(cases) >= 40


def test_judge_uses_the_rubric_and_reports_unavailable():
    from evaluation.judge import Verdict, judge, transcript
    from tests.unit.test_graph import FakeModel
    turns = [{"message": "Hi", "response": "Hello, I'm Mira.", "ui": [{"type": "specialist_notice", "reason": "handoff",
                                                                     "message": "A specialist will help"}]}]
    assert "specialist notice (handoff)" in transcript(turns)
    out = judge("Introduces itself.", turns, model=FakeModel(Verdict=[Verdict(passed=True, reason="It does.")]))
    assert out == {"passed": True, "reason": "It does."}
    down = judge("Introduces itself.", turns, model=FakeModel())
    assert down["passed"] is None and "unavailable" in down["reason"]


def test_welcome_back_check():
    from evaluation.assertions import welcome_back
    ui = [{"type": "welcome_back", "tour_title": "X", "quote_id": "new"}]
    r = run(turn())
    r.welcome = {"http": 200, "status": "ok", "quote_id": "new", "old_quote_id": "old", "price_usd": 315,
                 "engine_price_usd": 315, "ui": ui, "message": "Welcome back"}
    assert welcome_back(r, {"expect": "ok"}).passed
    r.welcome["price_usd"] = 300                                  # not what the engine says today
    assert not welcome_back(r, {"expect": "ok"}).passed
    r.welcome = {"http": 200, "status": "needs_specialist", "quote_id": None, "old_price_usd": 315,
                 "ui": [{**ui[0], "quote_id": None}], "message": "That price (USD 315) is no longer valid."}
    assert not welcome_back(r, {"expect": "needs_specialist"}).passed      # repeats the old price
    r.welcome["message"] = "That price is no longer valid."
    assert welcome_back(r, {"expect": "needs_specialist"}).passed
    assert welcome_back(r, None) is None


def test_content_approval_checks():
    from evaluation.assertions import content_approval
    r = run(turn(response="Hello, I'm Mira."))
    r.content = {"title": "Ella Railway", "traveller_publish": 401, "staff_publish": 403, "staff_status": "draft"}
    names = {c.name: c.passed for c in content_approval(r, {"state": "draft", "roles": True})}
    assert names == {"only_approver_publishes": True, "draft_never_shown": True}
    r.content["staff_publish"] = 200                                   # staff could publish: fail
    assert not content_approval(r, {"state": "draft", "roles": True})[0].passed
    shown = run(turn(ui=[{"type": "tour_card", "title": "Ella Railway"}]))
    shown.content = {"title": "Ella Railway"}
    assert not content_approval(shown, {"state": "draft"})[0].passed
    live = run(turn(retrieved=["T18"], cited=["T18"]))
    live.content = {"title": "X", "doc_id": "T18"}
    assert content_approval(live, {"state": "published"})[0].passed
    assert content_approval(run(turn()), None) == []
