"""A code-only reading of a message, used ONLY when every Gemini model has failed.

Gemini's free tier often returns 503 "high demand" or runs out of daily quota. Without this,
a turn whose analysis fails becomes a handoff, even for "2 adults, starting 3 May 2027".
Here plain rules pick out what a quote needs: the tour named, a start date, adults and
children's ages, plus a rough intent. Prices still come only from the pricing engine and the
reply wording for a quote is already code, so the quick-booker journeys keep working.

It reads only the latest message; earlier slots stay in the graph state. Trip planning
("a tour to Anuradhapura") is read from place names and trip words, so discovery keeps
working too. A message it still can't read gets the first discovery question (R1), not a
handoff: only an explicit request for a person goes to a specialist.
"""

from __future__ import annotations

import re
from datetime import date

from app.graph.tours import TOUR_ID, CatalogTour, _words
from app.llm.schemas import Intent, TripDetails, TurnAnalysis

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
MONTH = r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
         "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "a": 1, "an": 1}
NUM = r"(\d{1,2}|an?|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)"

DAY_MONTH = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?{MONTH}\b,?\s*(\d{{4}})?", re.I)
MONTH_DAY = re.compile(rf"\b{MONTH}\s+(\d{{1,2}})(?:st|nd|rd|th)?\b,?\s*(\d{{4}})?", re.I)
ISO = re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b")
ADULTS = re.compile(rf"\b{NUM}\s+(?:adults?|people|persons|pax|travell?ers|guests|grown-?ups)\b", re.I)
OF_US = re.compile(rf"\b{NUM}\s+of\s+us\b|\bthere (?:will be|are)\s+{NUM}\b", re.I)
SOLO = re.compile(r"\b(solo|just me|on my own|by myself|alone|only me)\b", re.I)
COUPLE = re.compile(r"\b(couple|two of us|my (?:wife|husband|partner|girlfriend|boyfriend) and (?:i|me))\b", re.I)
KIDS = re.compile(rf"\b{NUM}\s+(?:kids?|children|child|boys?|girls?|sons?|daughters?)\b", re.I)
AGES = re.compile(r"\bage[sd]?\s+((?:\d{1,2}\s*(?:,|and|&)?\s*)+)", re.I)
YEAR_OLD = re.compile(r"\b(\d{1,2})[- ]?(?:years?|yrs?|y)[- ]?olds?\b", re.I)
BABY = re.compile(r"\b(baby|infant|toddler)\b", re.I)
PRICE = re.compile(r"\b(price|how much|cost|quote|rate|update the price)\b", re.I)
BOOK = re.compile(r"\b(book|reserve)\b", re.I)
POLICY = re.compile(r"\b(cancel\w*|refund\w*|policy|payment|pay|deposit|insurance|visa)\b", re.I)
GREETING = re.compile(r"^\s*(hi|hello|hey|good (?:morning|afternoon|evening))\b[\s!.,]*$", re.I)
DISCOVER = re.compile(r"\b(suggest\w*|recommend\w*|ideas?|options?|what (?:should|can|could|would) (?:we|i)|"
                      r"where (?:should|can) (?:we|i)|plan (?:a|our|my))\b", re.I)
DAYS = re.compile(r"\b(\d{1,2})\s*(days?|nights?)\b", re.I)
TRIP = re.compile(r"\b(plan\w*|trip|tours?|holiday|vacation|itinerar\w*|visit\w*|travel\w*|"
                  r"go(?:ing)? to|explore|honeymoon|getaway)\b", re.I)
PERSON = re.compile(r"\b(?:talk|speak|chat)\s+(?:to|with)\s+(?:a\s+|an\s+|someone|somebody|"
                    r"(?:a\s+)?(?:real\s+)?(?:person|human|agent|specialist|consultant|staff))|"
                    r"\b(?:call|phone|ring)\s+me\b|\bhuman\b", re.I)
WEEKS = re.compile(r"\b(a|one|two|three|\d)\s+weeks?\b|\bfortnight\b", re.I)


def find_days(text: str) -> int | None:
    if m := DAYS.search(text):
        n = int(m[1])
        return n + 1 if m[2].lower().startswith("night") else n
    if m := WEEKS.search(text):
        return 14 if not m[1] else 7 * (int(m[1]) if m[1].isdigit() else WORDS[m[1].lower()])
    return None


def find_interests(text: str) -> list[str]:
    """Interest words the tour matcher knows ("beaches", "wildlife", "ancient"...)."""
    from app.graph.tours import INTEREST_PLACES
    keys = [k for group in INTEREST_PLACES for k in group]
    found = []
    for word in re.findall(r"[a-z]+", text.lower()):
        if any(word.startswith(k) for k in keys) and word not in found:
            found.append(word)
    return found


def find_places(text: str, tours: list[CatalogTour]) -> list[str]:
    """Sri Lankan places the message names, as written in our pages ("Nuwara Eliya")."""
    from app.rag.retriever import PLACES
    names = {p.replace("_", " ") for p in PLACES} | {d.replace("-", " ") for t in tours for d in t.destinations}
    low = text.lower().replace("-", " ")
    hits = [(m.start(), n) for n in names for m in re.finditer(rf"\b{re.escape(n)}\b", low)]
    out: list[str] = []
    for _, n in sorted(hits, key=lambda h: (h[0], -len(h[1]))):
        if not any(n in o.lower() for o in out):            # "galle fort" covers "galle"
            out.append(n.title())
    return out


def _num(word: str) -> int:
    return int(word) if word.isdigit() else WORDS[word.lower()]


def _date(day: int, month: str, year: str | None, today: date) -> date | None:
    m = MONTHS[month[:3].lower()]
    try:
        if year:
            return date(int(year), m, day)
        d = date(today.year, m, day)
        return d if d >= today else date(today.year + 1, m, day)
    except ValueError:
        return None


def find_date(text: str, today: date) -> date | None:
    if m := ISO.search(text):
        try:
            return date(int(m[1]), int(m[2]), int(m[3]))
        except ValueError:
            return None
    if m := DAY_MONTH.search(text):
        return _date(int(m[1]), m[2], m[3], today)
    if m := MONTH_DAY.search(text):
        return _date(int(m[2]), m[1], m[3], today)
    return None


def find_tour(text: str, tours: list[CatalogTour]) -> str | None:
    """The tour whose title the message names (most of the title's words, current pages first).
    Returns the tour's name so the graph's match_tour() maps it back to the same ID."""
    by_id = {t.tour_id: t for t in tours}
    if m := TOUR_ID.search(text):
        tid = f"T{int(m.group(1)):02d}"
        return by_id[tid].name if tid in by_id else None
    said = set(_words(text))
    best, best_key = None, None
    for t in tours:
        if not t.words:
            continue
        hits = len(said & t.words)
        share = hits / len(t.words)
        if share < 0.6 or (len(t.words) >= 3 and hits < 2):
            continue
        key = (share, hits, not t.stale)
        if best_key is None or key > best_key:
            best, best_key = t.name, key
    return best


def find_party(text: str) -> tuple[int | None, list[int], bool]:
    """(adults, child ages, a child was mentioned without an age)."""
    adults = None
    if m := ADULTS.search(text):
        adults = _num(m[1])
    elif SOLO.search(text):
        adults = 1
    elif COUPLE.search(text):
        adults = 2
    elif m := OF_US.search(text):
        adults = _num(m[1] or m[2])
    if m := AGES.search(text):                       # "aged 7 and 10"
        ages = [int(a) for a in re.findall(r"\d{1,2}", m[1])]
    else:                                            # "our 1-year-old", "a 5 year old"
        ages = [int(a) for a in YEAR_OLD.findall(text)]
    if not ages and BABY.search(text):
        ages = [0]
    kids = _num(m[1]) if (m := KIDS.search(text)) else len(ages)
    return adults, ages[:kids], kids > len(ages)


def quick_analysis(message: str, tours: list[CatalogTour], today: date) -> TurnAnalysis | None:
    tour = find_tour(message, tours)
    start = find_date(message, today)
    adults, ages, no_age = find_party(message)
    days, interests = find_days(message), find_interests(message)
    places = find_places(message, tours)
    has_slots = bool(tour or start or adults or ages)
    planning = (interests or days or places or DISCOVER.search(message)
                or (TRIP.search(message) and not tour and not POLICY.search(message)))
    if GREETING.match(message):
        intent, retrieval = Intent.GREETING, False
    elif PERSON.search(message):
        intent, retrieval = Intent.HANDOFF, False
    elif not tour and planning and (DISCOVER.search(message) or not PRICE.search(message)):
        intent, retrieval = Intent.DISCOVERY, False         # a planner: ask, then suggest tours
    elif BOOK.search(message) and has_slots:
        intent, retrieval = Intent.BOOK, False
    elif PRICE.search(message) or has_slots and not POLICY.search(message):
        intent, retrieval = Intent.QUOTE, False
    elif POLICY.search(message):
        intent, retrieval = Intent.POLICY, True
    else:                                 # can't tell what they want: ask the first question
        intent, retrieval = Intent.GREETING, False
    trip = TripDetails(tour_mention=tour, start_date=start, adults=adults, child_ages=ages,
                       interests=interests, destinations=places, days=days,
                       missing=["child_ages"] if no_age else [])
    return TurnAnalysis(intent=intent, tour_mention=tour, needs_retrieval=retrieval, trip=trip)
