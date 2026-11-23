"""Reading and writing Mira's records. The only module that turns pricing results into rows.

The traveller-facing read (get_public_quote) selects public columns only, so cost, margin
and GP% never leave the database on that path.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from typing import get_args

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Enquiry, EnquiryKind, Quote
from app.pricing import PublicQuote, QuoteResult


def save_quote(session: Session, result: QuoteResult, *, conversation_id: uuid.UUID | None = None,
               trace_id: str | None = None) -> Quote:
    """Store one calculate_quote() result: inputs, public and staff fields, or the reasons."""
    req = result.request
    row = Quote(status=result.status, conversation_id=conversation_id, trace_id=trace_id,
                tour_id=req.tour_id, start_date=req.start_date, adults=req.adults,
                child_ages=list(req.child_ages),
                reasons=[r.model_dump(mode="json") for r in result.reasons])
    if result.staff is not None:
        s, p = result.staff, result.staff.public
        row.tour_name, row.end_date = p.tour_name, p.end_date
        row.party_adults, row.party_children, row.party_infants = p.adults, p.children, p.infants
        row.price_usd, row.deposit_usd, row.balance_usd, row.balance_due = (
            p.price_usd, p.deposit_usd, p.balance_usd, p.balance_due)
        row.cost_lkr, row.cost_usd, row.fx_lkr_per_usd = s.cost_lkr, s.cost_usd, s.fx_lkr_per_usd
        row.margin, row.gp_pct, row.vehicle = s.margin, s.gp_pct, s.vehicle
        row.cost_lines = [line.model_dump(mode="json") for line in s.cost_lines]
        row.rate_rows = list(s.rate_rows)
    session.add(row)
    session.flush()
    return row


_PUBLIC_COLUMNS = (Quote.status, Quote.tour_id, Quote.tour_name, Quote.start_date, Quote.end_date,
                   Quote.party_adults, Quote.party_children, Quote.party_infants, Quote.price_usd,
                   Quote.deposit_usd, Quote.balance_usd, Quote.balance_due)


def get_public_quote(session: Session, quote_id: uuid.UUID) -> PublicQuote | None:
    """What a traveller may see of a stored quote; None if missing or not priced."""
    row = session.execute(select(*_PUBLIC_COLUMNS).where(Quote.id == quote_id)).one_or_none()
    if row is None or row.status != "ok":
        return None
    return PublicQuote(tour_id=row.tour_id, tour_name=row.tour_name, start_date=row.start_date,
                       end_date=row.end_date, adults=row.party_adults, children=row.party_children,
                       infants=row.party_infants, price_usd=row.price_usd, deposit_usd=row.deposit_usd,
                       balance_usd=row.balance_usd, balance_due=row.balance_due)


def create_enquiry(session: Session, kind: EnquiryKind, *, quote: Quote | None = None,
                   conversation_id: uuid.UUID | None = None, trace_id: str | None = None,
                   flags: Iterable[str] = (), notes: str | None = None,
                   contact: dict | None = None) -> Enquiry:
    """Record something staff must see (R7). A no-price quote's reason codes become its flags."""
    if kind not in get_args(EnquiryKind):
        raise ValueError(f"unknown enquiry kind {kind!r}")
    codes = [r["code"] for r in quote.reasons] if quote is not None else []
    flags = list(dict.fromkeys([*flags, *codes]))          # unique, in order
    if quote is not None:
        conversation_id = conversation_id or quote.conversation_id
        trace_id = trace_id or quote.trace_id
    row = Enquiry(kind=kind, quote_id=quote.id if quote else None, conversation_id=conversation_id,
                  trace_id=trace_id, flags=flags, notes=notes, contact=contact)
    session.add(row)
    session.flush()
    return row
