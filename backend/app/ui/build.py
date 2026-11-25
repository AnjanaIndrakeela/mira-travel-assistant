"""Code chooses the UI components from the verified state (step 11.13). No LLM involved.

- a priced quote with a saved quote_id -> tour_card + price_breakdown + booking_form
- no price, a custom trip, no answer or a handoff -> specialist_notice (code-written text)
- suggested tours -> one tour_card each, plus the day-by-day itinerary of the top one if
  it has parsed days (T07, T08, T09)
- a question about one tour -> its tour_card (and itinerary days)
- asking who is travelling -> traveller_picker
- cited sources -> source_list
- pictures: each tour card and itinerary day gets photos of the places it visits, and a trip
  the traveller described (places they named) gets a photo_gallery; all from app.ui.photos
Everything here is still checked by guards.ui_validator before it leaves the server.
"""

from __future__ import annotations

import re
from typing import Any

from app.rag.chunker import mask_money
from app.ui import photos
from app.ui.catalog import MONEY, UNSAFE, Accent

ACCENTS: tuple[Accent, ...] = ("teal", "leaf", "sun", "sky", "coral")
MAX_DAYS = 14

NOTICE: dict[str, str] = {
    "no_price": "Our team will check this trip and send you a confirmed price. "
                "Leave your email and we'll be in touch.",
    "custom_request": "Our team can plan a trip like this for you. Leave your email and we'll be in touch.",
    "unanswered_question": "Our team can answer this for you. Leave your email and they'll reply.",
    "handoff": "Leave your email and a travel specialist will get back to you.",
    "custom_plan": "None of these quite right? Our team can build a custom plan around your dates and "
                   "interests. We'll send you a price once it's planned.",
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
        "images": photos.for_tour(doc, 3),
    }


def itinerary_days(tour_id: str, *, content: Any) -> list[dict]:
    doc = content.get_published(tour_id)
    if doc is None or not doc.itinerary:
        return []
    src = {"doc_id": doc.id, "title": _clip(doc.title, 120)}
    days = doc.itinerary[:MAX_DAYS]
    pictures = photos.for_days([(d.title, d.description) for d in days])
    return [{"type": "itinerary_day", "tour_id": doc.id, "day": d.day,
             "title": _clip(mask_money(d.title, "tour"), 160),
             "description": _clip(mask_money(d.description, "tour"), 1200) or d.title,
             "meals": _clip(d.meals, 80) if d.meals else None,
             "stay": _clip(d.accommodation, 160) if d.accommodation else None,
             "source": src, "image": pic}
            for d, pic in zip(days, pictures)]


def photo_gallery(state: dict) -> dict | None:
    """Pictures of the places the traveller named (or their interests point to)."""
    from app.graph.tours import wanted_places
    named = [p for d in state.get("destinations") or [] for p in (photos.places_in(d) or [d])]
    places = named or sorted(wanted_places(state.get("interests") or [], []))
    images = photos.for_places(places, 6)
    if not images:
        return None
    names = [p.replace("-", " ").title() for p in dict.fromkeys(photos.ALIASES.get(p, p) for p in places)
             if p in photos.library() or photos.ALIASES.get(p) in photos.library()]
    title = "Places on your list" if not names else "Your trip: " + ", ".join(names[:4])
    return {"type": "photo_gallery", "title": _clip(title, 120), "images": images}


def plan_summary(state: dict) -> str | None:
    """What the traveller asked for, from the trip details, for the custom-plan enquiry."""
    parts = []
    if state.get("interests"):
        parts.append("Interests: " + ", ".join(state["interests"]))
    if state.get("destinations"):
        parts.append("Places: " + ", ".join(state["destinations"]))
    if state.get("duration_days"):
        parts.append(f"About {state['duration_days']} days")
    if party := state.get("party"):
        kids = party.get("child_ages") or []
        parts.append(f"{party['adults']} adult{'s' if party['adults'] != 1 else ''}"
                     + (f", children aged {', '.join(map(str, kids))}" if kids else ""))
    if state.get("start_date"):
        parts.append(f"From {state['start_date']}")
    elif state.get("travel_month"):
        parts.append(f"Month {state['travel_month']}")
    if not parts:
        return None
    text = _clip(". ".join(parts) + ".", 400)
    return None if UNSAFE.search(text) or MONEY.search(text) else text      # never invalid


def notice_reason(state: dict) -> str | None:
    if state.get("refusals") or state.get("unpriced_service"):
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
                       "fields": ["name", "email", "phone", "card"]})

    if state.get("assumed_tour") and not state.get("tour_cards"):
        # we picked the closest match: the other matches follow (all of them if none could be priced)
        shown = q["tour_id"] if q else None
        for tid in [t for t in state.get("suggested_tour_ids") or [] if t != shown][:2 if q else 3]:
            if card := tour_card(tid, content=content, rates=rates):
                ui.append(card)

    if reason := notice_reason(state):
        if reason == "custom_request" and (gallery := photo_gallery(state)):
            ui.append(gallery)
        # what happens next; the reason itself is already in the reply text
        ui.append({"type": "specialist_notice", "reason": reason, "message": NOTICE[reason],
                   "enquiry_id": state.get("enquiry_id")})

    if cards := state.get("tour_cards"):
        for c in cards:
            if card := tour_card(c["tour_id"], content=content, rates=rates, why=c.get("why")):
                ui.append(card)
        top = next((c["tour_id"] for c in cards if itinerary_days(c["tour_id"], content=content)), None)
        if top and action == "match_tours":
            ui.extend(itinerary_days(top, content=content))
        if action == "match_tours" and state.get("destinations") and (gallery := photo_gallery(state)):
            ui.insert(0, gallery)                          # the places they asked about, then the tours
        if action == "match_tours" and not reason:     # 12.3: offer a custom plan, never a price
            ui.append({"type": "specialist_notice", "reason": "custom_plan", "message": NOTICE["custom_plan"],
                       "enquiry_id": None, "summary": plan_summary(state)})
    elif (action == "retrieve" and state.get("intent") == "tour_info" and not q and not reason
          and state.get("tour_mention")                  # named in THIS message, not remembered
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

