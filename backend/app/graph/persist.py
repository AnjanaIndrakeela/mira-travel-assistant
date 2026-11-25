"""What the `persist` node writes (steps 9.3-9.4, R5-R7).

- Every price attempt is saved as a quote row: inputs, public fields, staff fields (cost,
  margin, GP%, rate rows) and the turn's trace_id. The StaffQuote is recomputed here from
  the stored request with the same engine, so it never has to travel through the graph state.
- Every quote gets a private enquiry for staff (R7): kind "quote" when priced, "no_price"
  when a specialist must confirm (flags = the reason codes, e.g. missing_rate).
- A tour we don't have, or a request for a person, becomes a "custom" enquiry.
- A price asked for a service with no rate row (an airport transfer...) becomes a flagged
  "no_price" enquiry with the traveller's words, so a specialist can quote it (R6).
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.db.repo import create_enquiry, save_quote
from app.pricing import QuoteRequest, calculate_quote
from app.visitors import remember

NOISE_FLAGS = {"output_guard"}       # about our reply, not something staff must act on
ENQUIRY_FLAGS = {"unpriced_service": "no_price", "custom_request": "custom", "handoff_requested": "custom"}


def _uuid(value: Any) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value)) if value else None
    except ValueError:
        return None


def plan_text(plan: dict, state: dict) -> str:
    """The draft plan as staff read it on the enquiry."""
    party = state.get("party") or {}
    kids = party.get("child_ages") or []
    who = (f"{party['adults']} adult(s)" + (f", children aged {', '.join(map(str, kids))}" if kids else "")
           if party else "not given")
    lines = [f"Draft plan written by Mira (not priced, not checked): {plan['title']}",
             f"Travellers: {who}. Start: {state.get('start_date') or 'not given'}.",
             plan["overview"], ""]
    lines += [f"Day {d['day']}: {d['title']} - {d['description']}"
              + (f" Stay: {d['stay']}." if d.get("stay") else "") for d in plan["days"]]
    lines += ["", "Sources: " + ", ".join(s["doc_id"] for s in plan.get("sources") or [])]
    return "\n".join(lines)[:4000]


def persist_turn(session: Session, state: dict, deps) -> dict:
    conversation_id = _uuid(state.get("conversation_id"))
    trace_id = state.get("trace_id")
    flags = [f for f in state.get("flags") or [] if f not in NOISE_FLAGS]
    out: dict = {}

    if (state.get("plan_shown") and (plan := state.get("trip_plan")) and state.get("trip_plan_key")
            and state.get("saved_plan_key") != state["trip_plan_key"]):
        # the planner agent's draft goes to staff to confirm and price, never live on its own
        enquiry = create_enquiry(session, "custom", conversation_id=conversation_id, trace_id=trace_id,
                                 flags=["generated_plan", "no_price"], notes=plan_text(plan, state))
        out.update(plan_enquiry_id=str(enquiry.id), saved_plan_key=state["trip_plan_key"])

    if req := state.get("quote_request"):
        result = calculate_quote(QuoteRequest(**req), rates=deps.rates, content=deps.content,
                                 today=deps.today, settings=deps.settings)
        quote = save_quote(session, result, conversation_id=conversation_id, trace_id=trace_id)
        kind = "quote" if result.status == "ok" else "no_price"
        enquiry = create_enquiry(session, kind, quote=quote, flags=flags,
                                 notes=f"Assumed tour {req['tour_id']} (closest suggestion)"
                                 if state.get("assumed_tour") else None)
        out.update(quote_id=str(quote.id), enquiry_id=str(enquiry.id))
        remember(session, state.get("visitor_id"), state, quote.id)        # R2
        return out
    if "plan_enquiry_id" in out:
        remember(session, state.get("visitor_id"), state)
        return out

    remember(session, state.get("visitor_id"), state)

    kind = next((ENQUIRY_FLAGS[f] for f in flags if f in ENQUIRY_FLAGS), None)
    if kind:
        last = next((m for m in reversed(state.get("messages") or []) if m.type == "human"), None)
        note = str(last.content)[:500] if last is not None else None     # already masked by the guard
        enquiry = create_enquiry(session, kind, conversation_id=conversation_id, trace_id=trace_id,
                                 flags=flags, notes=note)
        out["enquiry_id"] = str(enquiry.id)
    return out
