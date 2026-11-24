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

from sqlalchemy import select  # noqa: E402

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
    t.quote_id = str(res.quote_id) if res.quote_id else None
    if res.quote_id and (q := db.get(Quote, res.quote_id)):
        t.quote = {"status": q.status, "tour_id": q.tour_id, "price_usd": q.price_usd, "deposit_usd": q.deposit_usd,
                   "balance_usd": q.balance_usd, "cost_usd": float(q.cost_usd) if q.cost_usd is not None else None,
                   "reasons": [r["code"] for r in q.reasons], "trace_id": q.trace_id}
        t.recomputed = _recompute(q)
    e = db.get(Enquiry, res.enquiry_id) if res.enquiry_id else None
    if e is None and res.quote_id:            # the enquiry saved with this turn's quote
        e = db.scalar(select(Enquiry).where(Enquiry.quote_id == res.quote_id).order_by(Enquiry.created_at))
    if e is not None:
        t.enquiry = {"kind": e.kind, "flags": list(e.flags), "trace_id": e.trace_id, "id": str(e.id)}
        if "chat_error" in e.flags:                 # _turn's catch-all: the graph raised
            t.error = "chat turn failed (error handoff)"
    return t


def run_case(case: Case, graph, published: set[str]) -> CaseRun:
    from app.db.models import Conversation, Visitor
    from app.db.session import get_sessionmaker

    welcome = content = None
    with get_sessionmaker()() as db:
        if case.content:                                    # R8: seed (and maybe publish) an item
            content = _content_setup(case.content)
            if content.get("doc_id"):
                published = published | {content["doc_id"]}
        if case.returning:                                  # R2: a visitor who came before
            visitor, welcome = _returning_visitor(db, case.returning)
        else:
            visitor = db.get(Visitor, EVAL_VISITOR) or Visitor(id=EVAL_VISITOR)
        conv_id = uuid.uuid4()
        conv = Conversation(id=conv_id, visitor=visitor, thread_id=f"eval-{case.id}-{conv_id.hex[:8]}")
        db.add(conv)
        db.commit()
        db.refresh(conv)
        turns = [_record(db, graph, conv, msg) for msg in case.turns]
    run = CaseRun(case_id=case.id, turns=turns, published=published, tracing=_tracing(), welcome=welcome,
                  content=content)
    if content:
        _content_cleanup(content)
    if case.book:
        run.booking = _book(turns, case.book["card"])
    if case.check_access:
        run.access = _access(turns)
    return run


def _returning_visitor(db, spec: dict):
    """A new visitor whose last quote was priced on `priced_on`, then GET /visitors/{id}/welcome."""
    from datetime import date

    from app.db.models import Visitor
    from app.db.repo import save_quote
    from app.pricing import QuoteRequest, calculate_quote
    lq = spec["last_quote"]
    req = QuoteRequest(tour_id=lq["tour_id"], start_date=date.fromisoformat(lq["start_date"]),
                       adults=lq["adults"], child_ages=tuple(lq.get("child_ages", ())))
    old = save_quote(db, calculate_quote(req, today=date.fromisoformat(spec["priced_on"])))
    party = {"adults": lq["adults"], "child_ages": list(lq.get("child_ages", []))}
    visitor = Visitor(id=uuid.uuid4(), party=party, last_quote_id=old.id,
                      traveller_type={1: "solo", 2: "couple"}.get(lq["adults"], "group")
                      if not party["child_ages"] else "family")
    db.add(visitor)
    db.commit()
    c = _client()
    r = c.get(f"/api/v1/visitors/{visitor.id}/welcome")
    body = r.json() if r.status_code == 200 else {}
    out = {"http": r.status_code, "status": body.get("status"), "quote_id": body.get("quote_id"),
           "message": body.get("message"), "ui": body.get("ui"), "old_quote_id": str(old.id),
           "old_price_usd": old.price_usd}
    if out["quote_id"]:
        out["price_usd"] = c.get(f"/api/v1/quotes/{out['quote_id']}").json().get("price_usd")
        again = calculate_quote(req)                        # today's engine, independently
        out["engine_price_usd"] = again.staff.public.price_usd if again.staff else None
    db.refresh(visitor)
    return visitor, out


def _session_cookie(db, role: str):
    """A session for a password-less eval account of this role (no real password is used)."""
    from fastapi import Response

    from app.core.security import COOKIE, start_session
    from app.db.models import User
    email = f"eval-{role}@test.example"
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(email=email, role=role, password_hash="disabled")     # can't sign in with a password
        db.add(user)
        db.flush()
    r = Response()
    start_session(db, r, user, hours=0.5, secure=False)
    db.commit()
    return r.headers["set-cookie"].split(";")[0].split("=", 1)[1], COOKIE, user.id


def _content_setup(spec: dict) -> dict:
    """A content item written by code (no LLM: the drafting agent has its own tests), then the
    publish attempts the case asks for, through the real API and its role checks."""
    from app.db.models import ContentItem
    from app.db.session import get_sessionmaker
    from app.graph.content_workflow import DraftDay, TourDraft, to_markdown
    d = TourDraft(title=spec["title"], overview=spec["overview"],
                  days=[DraftDay(day=i + 1, title=t, description=x) for i, (t, x) in enumerate(spec["days"])])
    with get_sessionmaker()() as db:
        staff, cookie, staff_id = _session_cookie(db, "staff")
        approver, _, _ = _session_cookie(db, "approver")
        item = ContentItem(status="draft", type="tour", title=d.title, body=to_markdown(d), created_by=staff_id,
                           data={"command": "eval", "days": len(d.days), "places": spec.get("places", []),
                                 "itinerary": [x.model_dump() for x in d.days], "overview": d.overview})
        db.add(item)
        db.commit()
        item_id = str(item.id)
    out = {"item_id": item_id, "title": d.title, "doc_id": None}
    url = f"/api/v1/staff/content/{item_id}/publish"
    c = _client()
    out["traveller_publish"] = c.post(url).status_code
    if spec.get("roles"):
        c.cookies.set(cookie, staff)
        out["staff_publish"] = c.post(url).status_code
        out["staff_status"] = c.get(f"/api/v1/staff/content/{item_id}").json().get("status")
    if spec["state"] == "published":
        c.cookies.set(cookie, approver)
        r = c.post(url)
        out["approver_publish"] = r.status_code
        body = r.json() if r.status_code == 200 else {}
        out["doc_id"], out["indexed"] = body.get("doc_id"), body.get("indexed")
    return out


def _content_cleanup(content: dict) -> None:
    """Eval items don't stay: delete the row and take a published one out of the live library."""
    import faiss

    import app.rag as rag
    from app.data_loader import get_dataset
    from app.db.models import ContentItem
    from app.db.session import get_sessionmaker
    from app.graph.tours import refresh_live_tours
    from app.rag.index import VectorStore
    with get_sessionmaker()() as db:
        if item := db.get(ContentItem, uuid.UUID(content["item_id"])):
            db.delete(item)
            db.commit()
    if doc := content.get("doc_id"):
        ds = get_dataset()
        ds.content.docs[:] = [d for d in ds.content.docs if d.id != doc]
        refresh_live_tours(ds.content, ds.rates)
        if rag._retriever is not None:
            s = rag._retriever.store
            keep = [i for i, ch in enumerate(s.chunks) if ch.doc_id != doc]
            index = faiss.IndexFlatIP(s.index.d)
            index.add(s.index.reconstruct_n(0, s.index.ntotal)[keep])
            rag._retriever = type(rag._retriever)(VectorStore(index, [s.chunks[i] for i in keep], s.fingerprint),
                                                  rag._retriever.embed_query)


def _tracing() -> bool:
    from app.core.config import get_settings
    return get_settings().tracing_enabled


def _client():
    """The real API in-process (no server, no startup work: TestClient without `with`)."""
    from fastapi.testclient import TestClient

    from app.main import app
    return TestClient(app, raise_server_exceptions=False)


def _book(turns: list[TurnResult], card: str) -> dict:
    """POST /bookings for the last priced quote, as the booking form does."""
    from app.db.models import Enquiry
    from app.db.session import get_sessionmaker
    quote_id = next((t.quote_id for t in reversed(turns) if t.priced and t.quote_id), None)
    if quote_id is None:
        return {"status": "no_priced_quote"}
    full_card = {"holder": "Eval Traveller", "brand": "visa", "number": card, "exp_month": 12, "exp_year": 30,
                 "cvc": "123"}                     # the full mock card the booking form sends
    r = _client().post("/api/v1/bookings", json={"quote_id": quote_id, "card": full_card,
                                                  "contact": {"name": "Eval Traveller", "email": "eval@example.com"}})
    body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    out = {"http": r.status_code, "status": body.get("status"), "message": body.get("message"),
           "next_steps": body.get("next_steps")}
    with get_sessionmaker()() as db:          # the enquiry a failed payment must leave for staff
        e = db.scalar(select(Enquiry).where(Enquiry.quote_id == uuid.UUID(quote_id), Enquiry.kind == "booking_failed"))
        out["enquiry_kind"] = e.kind if e else None
    return out


def _access(turns: list[TurnResult]) -> dict:
    """A traveller (no staff session) tries to read the enquiry this chat created."""
    enquiry_id = next((t.enquiry["id"] for t in turns if t.enquiry and t.enquiry.get("id")), None)
    if enquiry_id is None:
        return {"public": None, "staff": None}
    c = _client()
    return {"public": c.get(f"/api/v1/enquiries/{enquiry_id}").status_code,
            "staff": c.get(f"/api/v1/staff/enquiries/{enquiry_id}").status_code}


def _judge(case: Case, run: CaseRun) -> dict | None:
    rubric = case.expected.get("behaviour")
    if not rubric or any(t.error for t in run.turns):
        return None
    from evaluation.judge import judge
    return judge(rubric, [{"message": t.message, "response": t.response, "ui": t.ui} for t in run.turns])


def evaluate(cases: list[Case], *, concurrency: int = 1, use_judge: bool = True, progress=print) -> list[dict]:
    from app.graph.build import build_graph
    graph = build_graph()                # one graph, a fresh thread per case
    published = _published()

    def one(case: Case) -> dict:
        run = run_case(case, graph, published)
        if use_judge:
            run.judge = _judge(case, run)
        checks = check_case(run, case.expected, case.retrieval, book=case.book, returning=case.returning,
                             content=case.content)
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
    p.add_argument("--no-judge", action="store_true", help="skip the LLM judge (code checks only)")
    p.add_argument("--baseline", action="store_true", help="also save reports/baseline_<date>.md")
    p.add_argument("--out", default=None, help="report name (default evaluation_report)")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    cases = load_cases(case_ids=args.cases, category=args.category, requirement=args.requirement)
    print(f"Running {len(cases)} case(s) with MIRA_TODAY={os.environ['MIRA_TODAY']}")
    started = time.time()
    results = evaluate(cases, concurrency=args.concurrency, use_judge=not args.no_judge)

    from evaluation.report import write_reports
    paths = write_reports(results, started=started, name=args.out, baseline=args.baseline,
                          partial=bool(args.cases or args.category or args.requirement))
    passed = sum(r["passed"] for r in results)
    print(f"\n{passed}/{len(results)} cases passed. Report: {', '.join(str(p) for p in paths)}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
