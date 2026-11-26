"""Returning visitors (R2, steps 17.2-17.5).

- remember(): after a turn, keep what is safe to reuse on the `visitors` row: the party
  (adults + child ages), the traveller type code derived from it, interests, and the last quote.
  No names, emails or phone numbers are stored here (the guard masks them anyway).
- known_slots(): what a new conversation can start with: interests, and last time's party as
  the traveller picker's starting point (Mira still asks who is travelling this time).
- welcome(): the last quote RE-RUN through the pricing engine with today's rates. A still-valid
  price is saved as a new quote row and shown by quote_id; a quote that no longer prices (date
  passed, rate expired) is never shown with its old price: specialist wording instead. A visitor
  who chatted before but never got a price is greeted with a welcome_back card with no trip.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import Quote, Visitor
from app.db.repo import save_quote
from app.pricing import QuoteRequest, calculate_quote

# The welcome_back card comes first and says "Welcome back" and the last trip, so the message
# carries on from it instead of repeating it; a still-valid price follows as its own card.
WELCOME_OK = ("I've re-checked the price with today's rates; it's below. Want to carry on with it, "
              "or plan something new?")
WELCOME_EXPIRED = ("That price is no longer valid ({why}), so I won't repeat it. Tell me new dates and "
                   "I'll price it again, or a specialist can help.")
WELCOME_AGAIN = "Where would you like to go this time? Ask me about a tour, a price or our policies."
WHY = {"date_in_past": "the start date has passed", "expired_rate": "the rate has expired",
       "missing_rate": "there's no current rate for it",
       "date_out_of_range": "rates aren't fixed for those dates yet"}


def _uuid(value: Any) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value)) if value else None
    except ValueError:
        return None


def remember(session: Session, visitor_id: Any, state: dict, quote_id: Any = None) -> None:
    visitor = session.get(Visitor, _uuid(visitor_id)) if _uuid(visitor_id) else None
    if visitor is None:
        return
    if party := state.get("party"):
        visitor.party = {"adults": int(party["adults"]), "child_ages": [int(a) for a in party["child_ages"]]}
    if state.get("traveller_type"):
        visitor.traveller_type = state["traveller_type"]
    if state.get("interests"):
        visitor.interests = list(dict.fromkeys([*visitor.interests, *state["interests"]]))[:10]
    if q := _uuid(quote_id):
        visitor.last_quote_id = q


def known_slots(session: Session, visitor_id: Any) -> dict:
    """State keys a new conversation starts with (empty for a first-time visitor)."""
    visitor = session.get(Visitor, _uuid(visitor_id)) if _uuid(visitor_id) else None
    if visitor is None or not (visitor.party or visitor.last_quote_id):
        return {"is_returning": False}
    out: dict = {"is_returning": True}
    if visitor.party and visitor.party.get("adults"):
        # not the party itself: Mira still asks who is travelling this time, and the
        # traveller picker starts from last time's answer
        out["remembered_party"] = {"adults": int(visitor.party["adults"]),
                                   "child_ages": [int(a) for a in visitor.party.get("child_ages", [])]}
    if visitor.interests:
        # a fallback only: a new request ("a trip to Galle") is matched on what it says, not on
        # interests from earlier trips
        out["remembered_interests"] = list(visitor.interests)
    return out


def welcome(session: Session, visitor_id: Any, deps=None) -> dict | None:
    """{"message", "ui", "quote_id", "status"} for a visitor who chatted before, else None.

    With a last quote: that trip, re-priced. Without one: a plain welcome back (status "again")."""
    visitor = session.get(Visitor, _uuid(visitor_id)) if _uuid(visitor_id) else None
    if visitor is None:
        return None
    old = session.get(Quote, visitor.last_quote_id) if visitor.last_quote_id else None
    if old is None:
        chatted = bool(visitor.conversations) or bool(visitor.party) or bool(visitor.interests)
        if not chatted:
            return None
        return {"status": "again", "quote_id": None, "message": WELCOME_AGAIN,
                "ui": [{"type": "welcome_back", "tour_title": None, "quote_id": None}]}
    req = QuoteRequest(tour_id=old.tour_id, start_date=old.start_date, adults=old.adults,
                       child_ages=tuple(old.child_ages or ()))
    if deps is None:                                    # the API: the engine's own defaults
        result = calculate_quote(req)
        doc = None
    else:
        result = calculate_quote(req, rates=deps.rates, content=deps.content, today=deps.today,
                                 settings=deps.settings)
        doc = deps.content.get(old.tour_id)
    title = (result.staff.public.tour_name if result.staff else None) or old.tour_name \
        or (doc.title if doc else old.tour_id)
    if result.status == "ok":
        fresh = save_quote(session, result)            # the re-verified price, a new row
        visitor.last_quote_id = fresh.id
        return {"status": "ok", "quote_id": str(fresh.id), "message": WELCOME_OK,
                "ui": [{"type": "welcome_back", "tour_title": title, "quote_id": str(fresh.id)},
                       {"type": "price_breakdown", "quote_id": str(fresh.id)}]}
    code = next((r.code.value for r in result.reasons), "")
    return {"status": result.status, "quote_id": None,
            "message": WELCOME_EXPIRED.format(why=WHY.get(code, "it needs a specialist to re-check")),
            "ui": [{"type": "welcome_back", "tour_title": title, "quote_id": None}]}
