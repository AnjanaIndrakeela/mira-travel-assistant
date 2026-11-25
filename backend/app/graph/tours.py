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
NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
                "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14}
# "5-night", "5 nights", "six-day", "7 days": a stated tour length (16.2)
LENGTH = re.compile(r"\b(\d{1,2}|" + "|".join(NUMBER_WORDS) + r")[\s-]*(nights?|days?)\b", re.IGNORECASE)

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
    expired: bool = False       # an offer past its dates: known by name, never suggested or priced


def catalog(content: ContentLibrary, rates: RateBook) -> list[CatalogTour]:
    """Published tours. Expired offers stay in the list, marked: a traveller can still ask for
    one by name, and the pricing engine then refuses it (stale_tour) so staff get a flagged
    enquiry. They are never suggested."""
    out = []
    for doc in content.by_type("tour"):
        rate = rates.tours.get(doc.id)
        m = re.search(r"(\d+)\s+days?", str(doc.meta.get("duration", "")), re.IGNORECASE)
        days = rate.days if rate else (int(m.group(1)) if m else None)
        out.append(CatalogTour(
            tour_id=doc.id, name=doc.title, duration=str(doc.meta.get("duration", "")), days=days,
            kind=rate.kind.value if rate else None, category=str(doc.meta.get("category", "")),
            destinations=tuple(slug(d) for d in doc.meta.get("destinations", [])), stale=doc.stale,
            words=frozenset(_words(doc.title)), text=f"{doc.title}\n{doc.body}".lower(),
            expired=bool(doc.expired_offer)))
    return out


def stated_days(text: str | None) -> int | None:
    """Tour length the words state, in days: "5-night" -> 6, "a 6-day trip" -> 6, else None."""
    if not text or not (m := LENGTH.search(text)):
        return None
    n = m.group(1).lower()
    n = int(n) if n.isdigit() else NUMBER_WORDS[n]
    return n + 1 if m.group(2).lower().startswith("night") else n


def _title_key(text: str) -> str:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return " ".join(words[1:] if words[:1] == ["the"] else words)


def match_tour(mention: str | None, tours: list[CatalogTour], context: str | None = None) -> str | None:
    """Best published tour for what the traveller wrote, or None if nothing fits well enough.

    `context` is the traveller's own message: the mention the LLM passes on can drop a stated
    length ("5-night"), and the length is what tells an older page from the current package.
    """
    if not mention or not mention.strip():
        return None
    by_id = {t.tour_id: t for t in tours}
    if m := TOUR_ID.search(mention):
        tid = f"T{int(m.group(1)):02d}"
        return tid if tid in by_id else None
    days = stated_days(mention) or stated_days(context)
    bare = LENGTH.sub(" ", mention)                 # the length picks between tours, it is not a title word
    want = set(_words(bare))
    if not want:
        return None
    title = _title_key(bare)
    best, best_key = None, None
    for t in tours:
        hits = len(want & t.words)
        score = hits / len(want)
        if score < MIN_MATCH:
            continue
        # higher share of the mention, then the stated length, then the exact title, then
        # current pages over older ones, then the share of the title covered, then similarity
        key = (score, days is not None and t.days == days, title == _title_key(t.name), not t.stale,
               hits / max(1, len(t.words)), SequenceMatcher(None, bare.lower(), t.name.lower()).ratio())
        if best_key is None or key > best_key:
            best, best_key = t.tour_id, key
    return best


def product_match(interests: list[str], destinations: list[str], tours: list[CatalogTour]) -> str | None:
    """A tour named by an activity rather than its title ("whale watching in Mirissa" -> T05).

    The LLM files such words as an interest, not a tour mention. Used only for an explicit
    price request with no tour named, and strict: at least two words, every one of them in a
    single current tour's title, and only one tour may fit.
    """
    phrases = [f"{i} {' '.join(destinations)}" for i in interests if destinations] + list(interests)
    for phrase in phrases:
        want = set(_words(phrase))
        if len(want) < 2:
            continue
        fits = [t.tour_id for t in tours if not t.stale and want <= t.words]
        if len(fits) == 1:
            return fits[0]
    return None


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
    """Top k published tours for a planner. No prices: cards carry facts and a reason only.

    Places the traveller NAMED count most; places that only follow from interests ("wildlife"
    -> Yala, Minneriya...) count half as much when places were named, so "a tour to
    Anuradhapura" shows tours that go there even if an earlier trip was about wildlife."""
    named = {slug(d) for d in destinations}
    from_interests = wanted_places(interests, []) - named
    interest_weight = 1.5 if named else 3.0
    scored = []
    for t in tours:
        if t.expired or (t.stale and t.kind is None):   # an expired offer, or an older page with no rates
            continue
        hit_named, hit_interest = named & set(t.destinations), from_interests & set(t.destinations)
        overlap = hit_named | hit_interest
        score = 3 * len(hit_named) / len(named) if named else 0.0
        if from_interests:
            score += interest_weight * len(hit_interest) / len(from_interests)
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


# R8: one shared list, refreshed in place when an approver publishes a tour, so every graph
# built from Deps.default() sees the new tour without a restart.
_LIVE: list[CatalogTour] = []


def live_tours(content: ContentLibrary, rates: RateBook) -> list[CatalogTour]:
    if not _LIVE:
        _LIVE.extend(catalog(content, rates))
    return _LIVE


def refresh_live_tours(content: ContentLibrary, rates: RateBook) -> None:
    _LIVE[:] = catalog(content, rates)
