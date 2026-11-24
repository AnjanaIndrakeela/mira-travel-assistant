"""Run the eval cases in-process against the real graph (step 14.1).

    python -m evaluation.runner                       # everything
    python -m evaluation.runner --case S02 --case S03 # some cases
    python -m evaluation.runner --category pricing    # one category (or --requirement R6)
    python -m evaluation.runner --baseline            # also save reports/baseline_<date>.md

Each case runs in a fresh conversation (its own LangGraph thread) through the same code as
POST /chat (app.api.chat._turn), with MIRA_TODAY=2026-11-19 and real Gemini calls. Quotes and
enquiries are saved like real chats, under one fixed "eval" visitor so staff can tell them apart,
and every turn is traced in Langfuse, so failing cases link to their traces.
"""

from __future__ import annotations

import os

os.environ["MIRA_TODAY"] = "2026-11-19"          # before any app import reads the settings

import argparse  # noqa: E402
import logging  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
import uuid  # noqa: E402
from concurrent.futures import ThreadPoolExecutor  # noqa: E402
from datetime import date  # noqa: E402

from evaluation.assertions import CaseRun, TurnResult, check_case  # noqa: E402
from evaluation.cases import Case, load_cases  # noqa: E402

logger = logging.getLogger("mira.eval")
EVAL_VISITOR = uuid.uuid5(uuid.NAMESPACE_URL, "https://mira.example/eval-visitor")
TODAY = date(2026, 11, 19)


def _published() -> set[str]:
    from app.data_loader import get_dataset
    return {d.id for d in get_dataset().content.published()}


def _recompute(quote) -> dict:
    from app.pricing import QuoteRequest, calculate_quote
    r = calculate_quote(QuoteRequest(tour_id=quote.tour_id, start_date=quote.start_date, adults=quote.adults,
                                     child_ages=tuple(quote.child_ages)), today=TODAY)
    if r.status != "ok":
        return {"status": r.status}
    return {"status": "ok", "price_usd": r.public.price_usd, "deposit_usd": r.public.deposit_usd}


def _invalid_ui(ui: list[dict]) -> list[str]:
    from app.ui.catalog import ADAPTER
    bad = []
    for c in ui:
        try:
            ADAPTER.validate_python(c)
        except Exception as exc:  # noqa: BLE001
            bad.append(f"{c.get('type')}: {exc.__class__.__name__}")
    return bad


def _record(db, graph, conv, message: str) -> TurnResult:
    from app.api.chat import _turn
    from app.api.staff import trace_url
    from app.db.models import Enquiry, Quote

    t = TurnResult(message=message)
    start = time.monotonic()
    try:
        res = _turn(db, graph, conv, message)
    except Exception as exc:  # noqa: BLE001  (the API never raises here; if it does, record it)
        t.error = f"{exc.__class__.__name__}: {exc}"[:300]
        t.seconds = time.monotonic() - start
        return t
    t.seconds = round(time.monotonic() - start, 2)
    state = graph.get_state({"configurable": {"thread_id": conv.thread_id}}).values or {}
    t.response, t.ui = res.message, [dict(c) for c in res.ui]
    t.cited = [s.doc_id for s in res.sources]
    t.ui_rejected = list(state.get("ui_rejected") or [])
    t.ui_invalid = _invalid_ui(t.ui)
    t.retrieved = list(dict.fromkeys(c.get("doc_id") for c in state.get("retrieved") or [] if c.get("doc_id")))
    t.abstain_reason = state.get("abstain_reason")
    t.action, t.intent = state.get("action"), state.get("intent")
    t.flags = list(state.get("flags") or [])
    t.llm_unavailable = "llm_unavailable" in t.flags
    t.questions_asked = int(state.get("questions_asked") or 0)
    t.trace_id = state.get("trace_id")
    t.trace_url = trace_url(t.trace_id)
    if res.quote_id and (q := db.get(Quote, res.quote_id)):
        t.quote = {"status": q.status, "tour_id": q.tour_id, "price_usd": q.price_usd, "deposit_usd": q.deposit_usd,
                   "balance_usd": q.balance_usd, "cost_usd": float(q.cost_usd) if q.cost_usd is not None else None,
                   "reasons": [r["code"] for r in q.reasons]}
        t.recomputed = _recompute(q)
    if res.enquiry_id and (e := db.get(Enquiry, res.enquiry_id)):
        t.enquiry = {"kind": e.kind, "flags": list(e.flags)}
        if "chat_error" in e.flags:                 # _turn's catch-all: the graph raised
            t.error = "chat turn failed (error handoff)"
    return t


def run_case(case: Case, graph, published: set[str]) -> CaseRun:
    from app.db.models import Conversation, Visitor
    from app.db.session import get_sessionmaker

    with get_sessionmaker()() as db:
        visitor = db.get(Visitor, EVAL_VISITOR) or Visitor(id=EVAL_VISITOR)
        conv_id = uuid.uuid4()
        conv = Conversation(id=conv_id, visitor=visitor, thread_id=f"eval-{case.id}-{conv_id.hex[:8]}")
        db.add(conv)
        db.commit()
        db.refresh(conv)
        turns = [_record(db, graph, conv, msg) for msg in case.turns]
    return CaseRun(case_id=case.id, turns=turns, published=published)


def evaluate(cases: list[Case], *, concurrency: int = 1, progress=print) -> list[dict]:
    from app.graph.build import build_graph
    graph = build_graph()                # one graph, a fresh thread per case
    published = _published()

    def one(case: Case) -> dict:
        run = run_case(case, graph, published)
        checks = check_case(run, case.expected, case.retrieval)
        passed = all(c.passed for c in checks)
        progress(f"{'PASS' if passed else 'FAIL'} {case.id:7} "
                 f"{sum(t.seconds for t in run.turns):5.1f}s "
                 f"{', '.join(c.name for c in checks if not c.passed)}")
        return {"case": case, "run": run, "checks": checks, "passed": passed}

    if concurrency <= 1:
        results = [one(c) for c in cases]
    else:
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            results = list(pool.map(one, cases))
    try:
        from app.graph.tracing import get_langfuse
        if lf := get_langfuse():
            lf.flush()
    except Exception:  # noqa: BLE001
        pass
    return results


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Run Mira's evaluation cases.")
    p.add_argument("--case", action="append", dest="cases", help="case ID (repeatable)")
    p.add_argument("--category")
    p.add_argument("--requirement")
    p.add_argument("--concurrency", type=int, default=1)
    p.add_argument("--baseline", action="store_true", help="also save reports/baseline_<date>.md")
    p.add_argument("--out", default=None, help="report name (default evaluation_report)")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    cases = load_cases(case_ids=args.cases, category=args.category, requirement=args.requirement)
    print(f"Running {len(cases)} case(s) with MIRA_TODAY={os.environ['MIRA_TODAY']}")
    started = time.time()
    results = evaluate(cases, concurrency=args.concurrency)

    from evaluation.report import write_reports
    paths = write_reports(results, started=started, name=args.out, baseline=args.baseline,
                          partial=bool(args.cases or args.category or args.requirement))
    passed = sum(r["passed"] for r in results)
    print(f"\n{passed}/{len(results)} cases passed. Report: {', '.join(str(p) for p in paths)}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
