"""Code chooses the UI components from the verified state (step 11.13). No LLM involved.

- a priced quote with a saved quote_id -> tour_card + price_breakdown + booking_form
- no price, a custom trip, no answer or a handoff -> specialist_notice (code-written text)
- suggested tours -> one tour_card each, plus the day-by-day itinerary of the top one if
  it has parsed days (T07, T08, T09)
- a question about one tour -> its tour_card (and itinerary days)
- asking who is travelling -> traveller_picker
- cited sources -> source_list
Everything here is still checked by guards.ui_validator before it leaves the server.
"""

from __future__ import annotations

import re
from typing import Any

from app.rag.chunker import mask_money
from app.ui.catalog import Accent

ACCENTS: tuple[Accent, ...] = ("teal", "leaf", "sun", "sky", "coral")
MAX_DAYS = 14

NOTICE: dict[str, str] = {
    "no_price": "A travel specialist needs to confirm this price, so I can't show one here. "
                "We can pass your trip to our team.",
    "custom_request": "We don't have that as a ready-made tour, but our team can plan it for you.",
    "unanswered_question": "I don't have that in our information. Our team can answer it for you.",
    "handoff": "A travel specialist can take it from here.",
}


def accent_for(tour_id: str) -> Accent:
    """One accent per card, stable for each tour."""
    digits = re.sub(r"\D", "", tour_id) or "0"
    return ACCENTS[int(digits) % len(ACCENTS)]


def _clip(text: str, n: int) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def _highlights(doc: Any) -> list[str]:
    section = next((s for s in doc.sections if s.heading.lower().startswith("highlight")), None)
    if section:
        items = [ln.lstrip("-* ").strip() for ln in section.text.splitlines() if ln.strip().startswith(("-", "*"))]
    else:
        items = [d.title for d in doc.itinerary]
    return [_clip(mask_money(i, "tour"), 160) for i in items if i][:3]


def tour_card(tour_id: str, *, content: Any, rates: Any, why: str | None = None) -> dict | None:
    doc = content.get_published(tour_id)
    if doc is None or doc.type != "tour":
        return None
    start = doc.meta.get("start")
    duration = str(doc.meta.get("duration", ""))
    if why and duration and why.startswith(duration):      # "6 nights / 7 days, visits X" -> "Visits X"
        why = why[len(duration):].lstrip(" ,") or None
        why = why[:1].upper() + why[1:] if why else None
    return {
        "type": "tour_card", "tour_id": doc.id, "title": _clip(doc.title, 120),
        "duration": _clip(str(doc.meta.get("duration", "")), 40) or "Ask us",
        "start": _clip(str(start), 120) if start else None,
        "highlights": _highlights(doc), "why": _clip(why, 200) if why else None,
        "accent": accent_for(doc.id),
        "bookable": doc.id in rates.tours and not doc.expired_offer,
        "source": {"doc_id": doc.id, "title": _clip(doc.title, 120)},
    }


def itinerary_days(tour_id: str, *, content: Any) -> list[dict]:
    doc = content.get_published(tour_id)
    if doc is None or not doc.itinerary:
        return []
    src = {"doc_id": doc.id, "title": _clip(doc.title, 120)}
    return [{"type": "itinerary_day", "tour_id": doc.id, "day": d.day,
             "title": _clip(mask_money(d.title, "tour"), 160),
             "description": _clip(mask_money(d.description, "tour"), 1200) or d.title,
             "meals": _clip(d.meals, 80) if d.meals else None,
             "stay": _clip(d.accommodation, 160) if d.accommodation else None,
             "source": src} for d in doc.itinerary[:MAX_DAYS]]


def notice_reason(state: dict) -> str | None:
    if state.get("refusals"):
        return "no_price"
    if state.get("unmatched_tour"):
        return "custom_request"
    if state.get("abstain_reason"):
        return "unanswered_question"
    if state.get("action") == "handoff":
        return "handoff"
    return None


def choose_components(state: dict, *, content: Any, rates: Any) -> list[dict]:
    ui: list[dict] = []
    q, quote_id = state.get("quote"), state.get("quote_id")
    action = state.get("action")

    if q:
        if card := tour_card(q["tour_id"], content=content, rates=rates):
            ui.append(card)
        if quote_id:      # without a saved quote there's nothing verified to fetch or book
            ui.append({"type": "price_breakdown", "quote_id": quote_id})
            ui.append({"type": "booking_form", "quote_id": quote_id,
                       "fields": ["name", "email", "card_number"]})

    if reason := notice_reason(state):
        refusals = list(dict.fromkeys(r["message"] for r in state.get("refusals") or []))
        message = " ".join(refusals) if reason == "no_price" and refusals else NOTICE[reason]
        ui.append({"type": "specialist_notice", "reason": reason, "message": _clip(message, 400),
                   "enquiry_id": state.get("enquiry_id")})

    if cards := state.get("tour_cards"):
        for c in cards:
            if card := tour_card(c["tour_id"], content=content, rates=rates, why=c.get("why")):
                ui.append(card)
        top = next((c["tour_id"] for c in cards if itinerary_days(c["tour_id"], content=content)), None)
        if top and action == "match_tours":
            ui.extend(itinerary_days(top, content=content))
    elif (action == "retrieve" and state.get("intent") == "tour_info" and not q
          and (tid := state.get("selected_tour_id"))):
        if card := tour_card(tid, content=content, rates=rates):
            ui.append(card)
            ui.extend(itinerary_days(tid, content=content))

    if state.get("question") and {"adults", "child_ages"} & set(state.get("missing") or []):
        party = state.get("party") or {}
        ui.append({"type": "traveller_picker", "adults": party.get("adults") or 2,
                   "child_ages": list(party.get("child_ages") or []),
                   "ask_child_ages": bool(state.get("children_without_age"))})

    retrieved = state.get("retrieved") or []
    items = [{"n": n, "doc_id": retrieved[n - 1]["doc_id"], "title": _clip(retrieved[n - 1]["title"], 120),
              "section": _clip(retrieved[n - 1]["section"] or "Overview", 160)}
             for n in state.get("citations") or [] if 1 <= n <= len(retrieved)]
    if items:
        ui.append({"type": "source_list", "items": items[:8]})
    return ui

