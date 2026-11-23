"""Quotes (step 9.5): the UI reads prices from here, never from the model.

GET  /quotes/{id}  -> PublicQuote only (the query selects public columns; no cost ever leaves)
POST /quotes       -> a direct quote from a form, through the same engine, saved with its
                      enquiry like a chat quote (R7)
"""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.db.repo import create_enquiry, get_public_quote, save_quote
from app.pricing import PublicQuote, QuoteRequest, calculate_quote

router = APIRouter(tags=["quotes"])


class QuoteOut(BaseModel):
    quote_id: uuid.UUID
    status: Literal["ok", "needs_specialist"]
    quote: PublicQuote | None = None
    messages: list[str] = []          # traveller-safe reasons when a specialist must confirm


@router.get("/quotes/{quote_id}", response_model=PublicQuote)
def read_quote(quote_id: uuid.UUID, db: Session = Depends(get_db)) -> PublicQuote:
    quote = get_public_quote(db, quote_id)
    if quote is None:
        raise HTTPException(404, "We couldn't find a priced quote with that ID.")
    return quote


@router.post("/quotes", response_model=QuoteOut)
def create_quote(req: QuoteRequest, db: Session = Depends(get_db)) -> QuoteOut:
    result = calculate_quote(req)
    row = save_quote(db, result)
    create_enquiry(db, "quote" if result.status == "ok" else "no_price", quote=row, flags=["direct_quote"])
    db.commit()
    return QuoteOut(quote_id=row.id, status=result.status,
                    quote=result.staff.public if result.staff else None,
                    messages=list(dict.fromkeys(r.message_traveller for r in result.reasons)))
