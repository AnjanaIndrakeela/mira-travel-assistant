"""Returning visitors (R2, step 17.4).

GET /visitors/{id}/welcome -> the welcome_back card with the LAST QUOTE RE-PRICED by the engine
today (a new quote row), or specialist wording with no old price when it no longer prices.
204 when the visitor is unknown or has no quote yet. The visitor ID is a random UUID the browser
keeps; nothing personal is returned (no names, emails or phones are stored on visitors).
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.guards.ui_validator import validate_ui
from app.ui.a2ui import to_a2ui
from app.visitors import welcome

router = APIRouter(tags=["visitors"])


class WelcomeOut(BaseModel):
    message: str
    ui: list[dict[str, Any]]
    a2ui: list[dict[str, Any]] = []      # the same cards as A2UI v1.0 messages: the welcome_back
                                         # surface first (shown above the message), then the price
    quote_id: uuid.UUID | None = None
    status: str


@router.get("/visitors/{visitor_id}/welcome", response_model=WelcomeOut,
            responses={204: {"description": "New visitor, or no earlier quote"}})
def visitor_welcome(visitor_id: uuid.UUID, db: Session = Depends(get_db)):
    out = welcome(db, visitor_id)
    if out is None:
        return Response(status_code=204)
    db.commit()
    ui, _ = validate_ui(out["ui"], quote_id=out["quote_id"])
    # two surfaces: the welcome_back card (shown above the message), then the price (below it)
    tag = uuid.uuid4().hex[:8]
    card = [c for c in ui if c["type"] == "welcome_back"]
    rest = [c for c in ui if c["type"] != "welcome_back"]
    return WelcomeOut(message=out["message"], ui=ui,
                      a2ui=to_a2ui(card, f"welcome-{tag}") + to_a2ui(rest, f"welcome-{tag}-price"),
                      quote_id=out["quote_id"], status=out["status"])
