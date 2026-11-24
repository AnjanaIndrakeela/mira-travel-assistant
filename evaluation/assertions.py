"""Code assertions for one case run (step 14.2, plan section 8.2).

Every check is a pure function over the recorded turns, so it is unit-tested without Gemini.
A check that doesn't apply to a case returns None and isn't counted.

- price_exact          quote cases: tour, price and deposit equal the expected numbers
- price_reverified     every priced quote equals calculate_quote() re-run on its stored inputs
- no_invented_amount   no currency amount in the reply or UI that isn't in a verified quote
                       (so a flag case may show no amount at all)
- no_price_when_flagged  flag cases: no priced quote, no price or booking card
- flag_saved           flag cases: a staff enquiry was saved with a flag (and the reason, if given)
- custom_enquiry       custom cases: a 'custom' enquiry was saved and no price was given
- ui_valid             every component passes the catalog schema; nothing had to be dropped
- no_draft_retrieved   every retrieved or cited document is published
- grounding            retrieval cases: must_cite retrieved and cited, must_not_cite never cited,
                       abstain cases cite nothing
- no_cost_leak         no cost, margin or GP% (field names, words or the cost figure) reaches
                       the traveller
- questions_le_3       Mira asked at most 3 slot questions in the whole conversation
- no_error             no turn crashed into the error handoff
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any

# currency amounts: "USD 2,965", "US$315", "$742", "LKR 667,000", "Rs. 500", "315 USD", "300 dollars"
_CUR = r"(?:USD|US\$|\$|LKR|Rs\.?|EUR|€|GBP|£)"
_NUM = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?"
AMOUNT = re.compile(rf"{_CUR}\s?({_NUM})|({_NUM})\s?(?:USD|LKR|dollars?|rupees?)\b", re.I)

COST_KEYS = ("cost_usd", "cost_lkr", "cost_lines", "gp_pct", "margin", "fx_lkr_per_usd", "rate_rows")
COST_WORDS = re.compile(r"\b(gross profit|profit margin|our margin|gp ?%|markup|mark-up|net rate|cost price)\b", re.I)


@dataclass
class TurnResult:
    message: str
    response: str = ""
    ui: list[dict[str, Any]] = field(default_factory=list)
    ui_rejected: list[dict[str, Any]] = field(default_factory=list)
    ui_invalid: list[str] = field(default_factory=list)          # schema errors found by the runner
    cited: list[str] = field(default_factory=list)                # doc IDs in the source list
    retrieved: list[str] = field(default_factory=list)            # doc IDs the retriever returned
    abstain_reason: str | None = None
    action: str | None = None
    intent: str | None = None
    flags: list[str] = field(default_factory=list)
    questions_asked: int = 0
    quote: dict[str, Any] | None = None       # saved quote: status, tour_id, price/deposit/balance, cost_usd
    recomputed: dict[str, Any] | None = None  # calculate_quote() on the stored inputs: status, price, deposit
    enquiry: dict[str, Any] | None = None     # saved enquiry: kind, flags
    trace_id: str | None = None
    trace_url: str | None = None
    llm_unavailable: bool = False
    seconds: float = 0.0
    error: str | None = None

    @property
    def priced(self) -> bool:
        return bool(self.quote and self.quote.get("status") == "ok")


@dataclass
class Check:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class CaseRun:
    case_id: str
    turns: list[TurnResult]
    published: set[str] = field(default_factory=set)

    def to_dict(self) -> dict:
        return {"case_id": self.case_id, "turns": [asdict(t) for t in self.turns]}


# ---- helpers ------------------------------------------------------------------------------------

def _num(s: str) -> float:
    return float(s.replace(",", ""))


def amounts(text: str) -> list[float]:
    """Every currency amount written in `text`."""
    return [_num(a or b) for a, b in AMOUNT.findall(text)]


def _ui_text(ui: list[dict]) -> str:
    return json.dumps(ui, ensure_ascii=False)


def _public_amounts(q: dict) -> set[float]:
    return {float(q[k]) for k in ("price_usd", "deposit_usd", "balance_usd") if q.get(k) is not None}


def _expected_quotes(expected: dict) -> list[dict]:
    if expected["type"] == "quote":
        return [expected]
    if expected["type"] == "quote_sequence":
        return expected["quotes"]
    return []


# ---- checks ---------------------------------------------------------------------------------------

def price_exact(run: CaseRun, expected: dict) -> Check | None:
    wanted = _expected_quotes(expected)
    if not wanted:
        return None
    got = [(t.quote["tour_id"], t.quote["price_usd"], t.quote["deposit_usd"]) for t in run.turns if t.priced]
    distinct = [g for i, g in enumerate(got) if i == 0 or g != got[i - 1]]      # same quote shown twice
    want = [(w["tour"], w["price_usd"], w["deposit_usd"]) for w in wanted]
    # the expected quotes, in order, among the quotes the conversation produced
    it = iter(distinct)
    ok = all(any(w == g for g in it) for w in want)
    if expected["type"] == "quote":            # a single quote: the LAST priced quote must be it
        ok = bool(distinct) and distinct[-1] == want[0]
    return Check("price_exact", ok, f"expected {want}, got {distinct or 'no priced quote'}")


def price_reverified(run: CaseRun) -> Check | None:
    priced = [t for t in run.turns if t.priced]
    if not priced:
        return None
    bad = [f"{t.quote['price_usd']}/{t.quote['deposit_usd']} vs engine "
           f"{(t.recomputed or {}).get('price_usd')}/{(t.recomputed or {}).get('deposit_usd')}"
           for t in priced
           if not t.recomputed or t.recomputed.get("status") != "ok"
           or (t.recomputed["price_usd"], t.recomputed["deposit_usd"]) != (t.quote["price_usd"], t.quote["deposit_usd"])]
    return Check("price_reverified", not bad, "; ".join(bad) or f"{len(priced)} quote(s) match the engine")


def no_invented_amount(run: CaseRun) -> Check:
    allowed: set[float] = set()
    bad = []
    for i, t in enumerate(run.turns, 1):
        if t.priced:
            allowed |= _public_amounts(t.quote)
        shown = amounts(t.response) + amounts(_ui_text(t.ui))
        bad += [f"turn {i}: {a:g}" for a in shown if a not in allowed]
    return Check("no_invented_amount", not bad,
                 ", ".join(bad) or f"all amounts are from verified quotes ({sorted(allowed) or 'none shown'})")


def no_price_when_flagged(run: CaseRun, expected: dict) -> Check | None:
    if expected["type"] != "flag_no_price":
        return None
    priced = [i for i, t in enumerate(run.turns, 1) if t.priced]
    cards = [i for i, t in enumerate(run.turns, 1)
             if any(c.get("type") in ("price_breakdown", "booking_form") for c in t.ui)]
    ok = not priced and not cards
    return Check("no_price_when_flagged", ok,
                 "no price given" if ok else f"priced on turn(s) {priced or cards}")


def flag_saved(run: CaseRun, expected: dict) -> Check | None:
    if expected["type"] != "flag_no_price":
        return None
    enquiries = [t.enquiry for t in run.turns if t.enquiry]
    flagged = [e for e in enquiries if e.get("flags")]
    reason = expected.get("reason")
    if reason:
        ok = any(reason in e["flags"] for e in flagged)
        detail = f"wanted flag '{reason}', saved {[e['flags'] for e in flagged] or 'no flagged enquiry'}"
    else:
        ok = bool(flagged)
        detail = f"saved {[(e['kind'], e['flags']) for e in flagged] or 'no flagged enquiry'}"
    return Check("flag_saved", ok, detail)


def custom_enquiry(run: CaseRun, expected: dict) -> Check | None:
    if expected["type"] != "custom_enquiry":
        return None
    kinds = [t.enquiry["kind"] for t in run.turns if t.enquiry]
    notice = any(c.get("type") == "specialist_notice" for t in run.turns for c in t.ui)
    ok = "custom" in kinds and not any(t.priced for t in run.turns[-1:]) and notice
    return Check("custom_enquiry", ok, f"enquiries {kinds or 'none'}, specialist notice {'shown' if notice else 'missing'}")


def ui_valid(run: CaseRun) -> Check:
    bad = [f"turn {i}: invalid {t.ui_invalid}" for i, t in enumerate(run.turns, 1) if t.ui_invalid]
    bad += [f"turn {i}: dropped {[r.get('type') for r in t.ui_rejected]}"
            for i, t in enumerate(run.turns, 1) if t.ui_rejected]
    n = sum(len(t.ui) for t in run.turns)
    return Check("ui_valid", not bad, "; ".join(bad) or f"{n} component(s) valid")


def no_draft_retrieved(run: CaseRun) -> Check | None:
    seen = {d for t in run.turns for d in [*t.retrieved, *t.cited]}
    if not seen or not run.published:
        return None
    bad = sorted(seen - run.published)
    return Check("no_draft_retrieved", not bad, f"unpublished: {bad}" if bad else f"{len(seen)} doc(s), all published")


def grounding(run: CaseRun, retrieval: dict | None) -> Check | None:
    if not retrieval:
        return None
    last = run.turns[-1]
    retrieved, cited = set(last.retrieved), set(last.cited)
    problems = []
    if retrieval.get("abstain"):
        if cited:
            problems.append(f"should abstain but cited {sorted(cited)}")
    else:
        must = set(retrieval.get("must_cite", []))
        if must - retrieved:
            problems.append(f"not retrieved: {sorted(must - retrieved)}")
        if must and not must & cited:
            problems.append(f"cited none of {sorted(must)} (cited {sorted(cited) or 'nothing'})")
    wrong = set(retrieval.get("must_not_cite", [])) & cited
    if wrong:
        problems.append(f"cited {sorted(wrong)}")
    return Check("grounding", not problems, "; ".join(problems) or f"cited {sorted(cited) or 'nothing (abstained)'}")


def no_cost_leak(run: CaseRun) -> Check:
    bad = []
    for i, t in enumerate(run.turns, 1):
        ui = _ui_text(t.ui).lower()
        bad += [f"turn {i}: UI field {k}" for k in COST_KEYS if f'"{k}"' in ui]
        if m := COST_WORDS.search(t.response):
            bad.append(f"turn {i}: '{m.group(0)}'")
        cost = (t.quote or {}).get("cost_usd")
        if cost is not None and t.priced:
            shown = set(amounts(t.response) + amounts(_ui_text(t.ui)))
            figure = {round(float(cost)), round(float(cost), 2)} - _public_amounts(t.quote)
            if shown & figure:
                bad.append(f"turn {i}: cost figure {cost}")
    return Check("no_cost_leak", not bad, "; ".join(bad) or "no cost, margin or GP% shown")


def questions_le_3(run: CaseRun) -> Check:
    n = max((t.questions_asked for t in run.turns), default=0)
    return Check("questions_le_3", n <= 3, f"{n} question(s) asked")


def no_error(run: CaseRun) -> Check:
    bad = [f"turn {i}: {t.error}" for i, t in enumerate(run.turns, 1) if t.error]
    return Check("no_error", not bad, "; ".join(bad) or "every turn answered")


def check_case(run: CaseRun, expected: dict, retrieval: dict | None = None) -> list[Check]:
    checks = [no_error(run), price_exact(run, expected), price_reverified(run), no_invented_amount(run),
              no_price_when_flagged(run, expected), flag_saved(run, expected), custom_enquiry(run, expected),
              ui_valid(run), no_draft_retrieved(run), grounding(run, retrieval), no_cost_leak(run),
              questions_le_3(run)]
    return [c for c in checks if c is not None]
