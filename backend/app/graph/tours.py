"""Tour lookups the graph does in code, not in the LLM (steps 8.3, 8.4, 8.9).

- match_tour(): the traveller's words -> one tour ID, using PUBLISHED tours only (a draft
  such as T15 can never be matched, quoted or suggested).
- traveller_type(): solo / couple / family / group, from the party.
- suggest_tours(): the planner's top 3 by destination overlap, interests and duration.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from app.data_loader.content_loader import ContentLibrary
from app.data_loader.rate_loader import RateBook
from app.graph.state import Party, TourCard, TravellerType

TOUR_ID = re.compile(r"\bT-?(\d{1,2})\b", re.IGNORECASE)
# Words that say nothing about WHICH tour (they appear in many titles or in how people ask).
STOP = {"the", "a", "an", "and", "of", "in", "to", "from", "for", "on", "tour", "tours", "package",
        "trip", "sri", "lanka", "lankan", "your", "our", "one", "that", "this", "with", "day"}
MIN_MATCH = 0.6           # share of the traveller's words that must appear in the title

# Interest words -> the dataset's destination slugs they point to.
INTEREST_PLACES: dict[tuple[str, ...], set[str]] = {
    ("cultur", "ancient", "heritage", "histor", "temple", "ruin", "triangle", "unesco"):
        {"anuradhapura", "polonnaruwa", "sigiriya", "kandy"},
    ("beach", "sea", "coast", "surf", "swim", "sun", "relax"): {"mirissa", "galle", "hikkaduwa"},
    ("wildlife", "safari", "animal", "elephant", "leopard", "bird", "jungle"):
        {"yala", "udawalawe", "minneriya"},
    ("whale", "dolphin"): {"mirissa"},
    ("hill", "tea", "mountain", "train", "hik", "walk", "cool", "climb", "peak", "trek"):
        {"nuwara-eliya", "ella", "kandy"},
    ("photo",): {"yala", "udawalawe"},
    ("city", "food", "shop", "colonial", "fort"): {"colombo", "galle"},
}


DEFAULT_PICKS = ("T09", "T08", "T05")    # a round trip, the highlights, a day trip


def is_place(mention: str, tours: list[CatalogTour]) -> bool:
    """True if the words name a place ("Yala", "Jaffna"), not a tour."""
    from app.rag.retriever import PLACES
    key = mention.strip().lower()
    places = {p.replace("_", " ") for p in PLACES} | {d.replace("-", " ") for t in tours
                                                      for d in t.destinations}
    return key.replace("-", " ") in places


def _words(text: str) -> list[str]:
    out = []
    for w in re.findall(r"[a-z0-9]+", text.lower().replace("’", "'").replace("'s", "")):
        if w in STOP:
            continue
        out.append(w[:-1] if len(w) > 4 and w.endswith("s") else w)   # treasures -> treasure
    return out


def slug(place: str) -> str:
    return re.sub(r"[^a-z]+", "-", place.lower()).strip("-")


@dataclass(frozen=True)
class CatalogTour:
    tour_id: str
    name: str
    duration: str
    days: int | None
    kind: str | None            # "day" | "multi_day" | None (no rate row: quoted individually)
    category: str
    destinations: tuple[str, ...]
    stale: bool                 # older page, or replaced by a newer tour
    words: frozenset[str]
    text: str                   # title + body, lower case, for interest words


def catalog(content: ContentLibrary, rates: RateBook) -> list[CatalogTour]:
    """Published tours only, minus expired offers."""
    out = []
    for doc in content.by_type("tour"):
        if doc.expired_offer:
            continue
        rate = rates.tours.get(doc.id)
        m = re.search(r"(\d+)\s+days?", str(doc.meta.get("duration", "")), re.IGNORECASE)
        days = rate.days if rate else (int(m.group(1)) if m else None)
        out.append(CatalogTour(
            tour_id=doc.id, name=doc.title, duration=str(doc.meta.get("duration", "")), days=days,
            kind=rate.kind.value if rate else None, category=str(doc.meta.get("category", "")),
            destinations=tuple(slug(d) for d in doc.meta.get("destinations", [])), stale=doc.stale,
            words=frozenset(_words(doc.title)), text=f"{doc.title}\n{doc.body}".lower()))
    return out


def match_tour(mention: str | None, tours: list[CatalogTour]) -> str | None:
    """Best published tour for what the traveller wrote, or None if nothing fits well enough."""
    if not mention or not mention.strip():
        return None
    by_id = {t.tour_id: t for t in tours}
    if m := TOUR_ID.search(mention):
        tid = f"T{int(m.group(1)):02d}"
        return tid if tid in by_id else None
    want = set(_words(mention))
    if not want:
        return None
    best, best_key = None, None
    for t in tours:
        hits = len(want & t.words)
        score = hits / len(want)
        if score < MIN_MATCH:
            continue
        # higher share of the mention, then current pages over older ones, then the share
        # of the title covered, then plain string similarity
        key = (score, not t.stale, hits / max(1, len(t.words)),
               SequenceMatcher(None, mention.lower(), t.name.lower()).ratio())
        if best_key is None or key > best_key:
            best, best_key = t.tour_id, key
    return best


def traveller_type(party: Party | None) -> TravellerType | None:
    """Decided by code from the party (step 8.4), never by the LLM."""
    if not party:
        return None
    if party["child_ages"]:
        return "family"
    return {0: None, 1: "solo", 2: "couple"}.get(party["adults"], "group")


def wanted_places(interests: list[str], destinations: list[str]) -> set[str]:
    places = {slug(d) for d in destinations}
    for interest in interests:
        low = interest.lower()
        for keys, slugs in INTEREST_PLACES.items():
            if any(k in low for k in keys):
                places |= slugs
    return places


def suggest_tours(tours: list[CatalogTour], *, interests: list[str], destinations: list[str],
                  days: int | None, trip_type: str | None = None, k: int = 3) -> list[TourCard]:
    """Top k published tours for a planner. No prices: cards carry facts and a reason only."""
    places = wanted_places(interests, destinations)
    scored = []
    for t in tours:
        if t.stale and t.kind is None:        # an older page with no rates: replaced, skip it
            continue
        overlap = places & set(t.destinations)
        score = 3 * len(overlap) / max(1, len(places)) if places else 0.0
        score += sum(0.3 for i in interests if i and i.lower()[:5] in t.text)
        if days and t.days:
            score += 1 - min(1.0, abs(t.days - days) / days)
        if trip_type == "day" and t.kind == "day" or trip_type == "multi_day" and t.kind == "multi_day":
            score += 0.5
        if t.stale:
            score -= 0.5
        scored.append((score, t, overlap))
    scored.sort(key=lambda s: (-s[0], s[1].tour_id))
    picked = [s for s in scored if s[0] > 0][:k]
    if not picked:                            # nothing to go on: a short, varied default set
        picked = [s for s in scored if s[1].tour_id in DEFAULT_PICKS][:k]
    cards: list[TourCard] = []
    for score, t, overlap in picked:
        visits = ", ".join(p.replace("-", " ").title() for p in (sorted(overlap) or t.destinations[:3]))
        cards.append(TourCard(tour_id=t.tour_id, name=t.name, duration=t.duration,
                              destinations=list(t.destinations), why=f"{t.duration}, visits {visits}"))
    return cards
