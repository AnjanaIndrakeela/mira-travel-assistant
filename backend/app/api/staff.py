"""Staff sign-in and the enquiry console (steps 13.2-13.4, R7).

/auth/login, /auth/logout, /auth/me: a session cookie (app.core.security).
/staff/*: signed-in staff or approvers only (require_role, code not prompts). These are the
only responses that carry cost, margin and GP%, plus the traveller's contact details.

Notes are append-only (no edit or delete route; a database trigger refuses UPDATE/DELETE).
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime
from decimal import Decimal
from functools import lru_cache
from typing import Any, Literal, get_args

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_chat_graph, get_db
from app.core.config import get_settings
from app.core.security import (authenticate, current_user, end_session, login_limiter,
                               require_role, start_session)
from app.db.models import Conversation, Enquiry, EnquiryNote, EnquiryStatus, Quote

logger = logging.getLogger("mira.staff")
router = APIRouter()

# flags that are information only; anything else means a person should look at it first
INFO_FLAGS = {"direct_quote", "from_traveller"}


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# ---- auth --------------------------------------------------------------------------------------

class LoginRequest(_In):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=200)


class Me(BaseModel):
    email: str
    role: str


BAD_LOGIN = "That email and password don't match an account."


@router.post("/auth/login", response_model=Me, tags=["auth"])
def login(req: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)) -> Me:
    keys = (f"email:{req.email.lower()}", f"ip:{request.client.host if request.client else '-'}")
    if login_limiter.blocked(*keys):
        raise HTTPException(429, "Too many sign-in attempts. Please wait a few minutes.")
    user = authenticate(db, req.email, req.password)
    if user is None:
        login_limiter.failed(*keys)
        logger.info("staff sign-in failed")
        raise HTTPException(401, BAD_LOGIN)
    login_limiter.clear(*keys)
    s = get_settings()
    start_session(db, response, user, hours=s.mira_session_hours, secure=s.mira_cookie_secure)
    db.commit()
    return Me(email=user.email, role=user.role)


@router.post("/auth/logout", status_code=204, tags=["auth"])
def logout(request: Request, db: Session = Depends(get_db)) -> Response:
    response = Response(status_code=204)
    end_session(db, request, response)
    db.commit()
    return response


@router.get("/auth/me", response_model=Me, tags=["auth"])
def me(user=Depends(current_user)) -> Me:
    return Me(email=user.email, role=user.role)


# ---- enquiries ---------------------------------------------------------------------------------

class EnquiryRow(BaseModel):
    id: uuid.UUID
    kind: str
    status: str
    flagged: bool
    flags: list[str]
    created_at: datetime
    tour_id: str | None = None
    tour_name: str | None = None
    start_date: date | None = None
    price_usd: int | None = None
    contact_name: str | None = None
    note_count: int = 0


class EnquiryList(BaseModel):
    enquiries: list[EnquiryRow]
    counts: dict[str, int]                  # per status, for the filter tabs


class NoteOut(BaseModel):
    id: uuid.UUID
    body: str
    author: str
    created_at: datetime


class StaffQuoteOut(BaseModel):
    """Everything about the quote, including the numbers travellers never see."""
    id: uuid.UUID
    status: str
    tour_id: str
    tour_name: str | None
    start_date: date
    end_date: date | None
    adults: int
    child_ages: list[int]
    price_usd: int | None
    deposit_usd: int | None
    balance_usd: int | None
    balance_due: date | None
    cost_usd: Decimal | None
    cost_lkr: Decimal | None
    fx_lkr_per_usd: Decimal | None
    margin: Decimal | None
    gp_pct: Decimal | None
    vehicle: str | None
    cost_lines: list[dict[str, Any]] | None
    reasons: list[dict[str, Any]]


class ChatLine(BaseModel):
    role: Literal["traveller", "mira"]
    text: str


class EnquiryDetail(BaseModel):
    id: uuid.UUID
    kind: str
    status: str
    flagged: bool
    flags: list[str]
    created_at: datetime
    updated_at: datetime
    contact: dict[str, Any] | None
    traveller_notes: str | None
    quote: StaffQuoteOut | None
    trace_id: str | None
    trace_url: str | None
    conversation_id: uuid.UUID | None
    conversation: list[ChatLine]
    notes: list[NoteOut]


class NoteRequest(_In):
    body: str = Field(min_length=1, max_length=4000)


class StatusRequest(_In):
    status: EnquiryStatus


def is_flagged(flags: list[str]) -> bool:
    return any(f not in INFO_FLAGS for f in flags)


def tour_name(quote: Quote | None) -> str | None:
    """The quote's tour name; an unpriced quote doesn't store one, so take it from the rate sheet."""
    if quote is None:
        return None
    if quote.tour_name:
        return quote.tour_name
    from app.data_loader import get_dataset
    rate = get_dataset().rates.tours.get(quote.tour_id)
    return rate.name if rate else None


@lru_cache(maxsize=1)
def _langfuse_for_links():
    from app.graph.tracing import get_langfuse
    return get_langfuse()


def trace_url(trace_id: str | None) -> str | None:
    """A link to the trace in Langfuse, or None when tracing is off or the lookup fails."""
    if not trace_id:
        return None
    s = get_settings()
    if s.langfuse_project_id:
        return f"{s.langfuse_host.rstrip('/')}/project/{s.langfuse_project_id}/traces/{trace_id}"
    try:
        lf = _langfuse_for_links()
        return lf.get_trace_url(trace_id=trace_id) if lf else None
    except Exception as exc:  # noqa: BLE001  (Langfuse unreachable: the page still works)
        logger.warning("no trace link: %s", exc.__class__.__name__)
        return None


def _get_enquiry(db: Session, enquiry_id: uuid.UUID) -> Enquiry:
    row = db.get(Enquiry, enquiry_id)
    if row is None:
        raise HTTPException(404, "We couldn't find that enquiry.")
    return row


def _transcript(db: Session, graph, conversation_id: uuid.UUID | None) -> list[ChatLine]:
    """The chat as the graph remembers it (in memory: empty after a server restart)."""
    conv = db.get(Conversation, conversation_id) if conversation_id else None
    if conv is None:
        return []
    try:
        from langchain_core.messages import HumanMessage

        from app.api.chat import text_of
        state = graph.get_state({"configurable": {"thread_id": conv.thread_id}}).values or {}
        return [ChatLine(role="traveller" if isinstance(m, HumanMessage) else "mira", text=text_of(m))
                for m in state.get("messages", [])]
    except Exception as exc:  # noqa: BLE001
        logger.warning("no transcript: %s", exc.__class__.__name__)
        return []


@router.get("/staff/enquiries", response_model=EnquiryList, tags=["staff"])
def list_enquiries(status: EnquiryStatus | None = Query(default=None),
                   flagged: bool | None = Query(default=None),
                   limit: int = Query(default=200, ge=1, le=500),
                   db: Session = Depends(get_db), user=Depends(require_role("staff"))) -> EnquiryList:
    notes = (select(EnquiryNote.enquiry_id, func.count().label("n"))
             .group_by(EnquiryNote.enquiry_id).subquery())
    q = (select(Enquiry, Quote, notes.c.n)
         .outerjoin(Quote, Quote.id == Enquiry.quote_id)
         .outerjoin(notes, notes.c.enquiry_id == Enquiry.id)
         .order_by(Enquiry.created_at.desc()))
    if status:
        q = q.where(Enquiry.status == status)
    rows = []
    for e, quote, n in db.execute(q.limit(limit)):
        row = EnquiryRow(id=e.id, kind=e.kind, status=e.status, flagged=is_flagged(e.flags), flags=e.flags,
                         created_at=e.created_at, note_count=n or 0,
                         contact_name=(e.contact or {}).get("name"),
                         tour_id=quote.tour_id if quote else None,
                         tour_name=tour_name(quote),
                         start_date=quote.start_date if quote else None,
                         price_usd=quote.price_usd if quote else None)
        if flagged is None or row.flagged == flagged:
            rows.append(row)
    rows.sort(key=lambda r: not r.flagged)               # flagged first; newest first within each
    counts = {s: 0 for s in get_args(EnquiryStatus)}
    for s, n in db.execute(select(Enquiry.status, func.count()).group_by(Enquiry.status)):
        counts[s] = n
    return EnquiryList(enquiries=rows, counts=counts)


@router.get("/staff/enquiries/{enquiry_id}", response_model=EnquiryDetail, tags=["staff"])
def get_enquiry(enquiry_id: uuid.UUID, db: Session = Depends(get_db), graph=Depends(get_chat_graph),
                user=Depends(require_role("staff"))) -> EnquiryDetail:
    e = _get_enquiry(db, enquiry_id)
    quote = db.get(Quote, e.quote_id) if e.quote_id else None
    notes = db.scalars(select(EnquiryNote).where(EnquiryNote.enquiry_id == e.id)
                       .order_by(EnquiryNote.created_at)).all()
    trace_id = e.trace_id or (quote.trace_id if quote else None)
    return EnquiryDetail(
        id=e.id, kind=e.kind, status=e.status, flagged=is_flagged(e.flags), flags=e.flags,
        created_at=e.created_at, updated_at=e.updated_at, contact=e.contact, traveller_notes=e.notes,
        quote=(StaffQuoteOut.model_validate(quote, from_attributes=True).model_copy(update={"tour_name": tour_name(quote)})
               if quote else None),
        trace_id=trace_id, trace_url=trace_url(trace_id),
        conversation_id=e.conversation_id, conversation=_transcript(db, graph, e.conversation_id),
        notes=[NoteOut(id=n.id, body=n.body, author=n.author.email, created_at=n.created_at) for n in notes])


@router.post("/staff/enquiries/{enquiry_id}/notes", response_model=NoteOut, status_code=201, tags=["staff"])
def add_note(enquiry_id: uuid.UUID, req: NoteRequest, db: Session = Depends(get_db),
             user=Depends(require_role("staff"))) -> NoteOut:
    e = _get_enquiry(db, enquiry_id)
    note = EnquiryNote(enquiry_id=e.id, author_id=user.id, body=req.body)
    db.add(note)
    db.flush()
    db.commit()
    return NoteOut(id=note.id, body=note.body, author=user.email, created_at=note.created_at)


@router.patch("/staff/enquiries/{enquiry_id}/status", response_model=EnquiryRow, tags=["staff"])
def set_status(enquiry_id: uuid.UUID, req: StatusRequest, db: Session = Depends(get_db),
               user=Depends(require_role("staff"))) -> EnquiryRow:
    e = _get_enquiry(db, enquiry_id)
    if e.status != req.status:              # the change is kept in the append-only notes too
        db.add(EnquiryNote(enquiry_id=e.id, author_id=user.id, body=f"Status changed from {e.status} to {req.status}."))
        e.status = req.status
    db.flush()
    db.commit()
    return EnquiryRow(id=e.id, kind=e.kind, status=e.status, flagged=is_flagged(e.flags), flags=e.flags,
                      created_at=e.created_at, contact_name=(e.contact or {}).get("name"))
