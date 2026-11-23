"""Reply text that code writes, without the LLM.

Used for turns where the LLM adds nothing but risk (an injection, an off-topic request), for
the exact quote wording, and as the fallback for every action when Gemini is unavailable,
so a chat turn always gets a sensible reply (step 8.17, plan §16).
"""

from __future__ import annotations

from datetime import date

from app.graph.state import Slot

UNKNOWN_INFO = ("I don't have that information in our travel content. I can pass your question "
                "to a travel specialist, who will get back to you.")
SPECIALIST_PRICE = "A travel specialist will confirm the price for these dates and get back to you."
DECLINE = ("I can't change our prices or offer discounts in this chat, and I keep to our normal "
           "booking rules. I'm happy to give you a standard quote, though.")
OFF_TOPIC = ("I can only help with holidays in Sri Lanka with Ceylon Compass Holidays. "
             "Shall we plan a trip? Tell me what you'd like to see, or a tour you have in mind.")
GREETING = ("Hello, I'm Mira from Ceylon Compass Holidays. I can suggest tours, answer questions "
            "about them and our policies, and give you an instant price.")
HANDOFF = ("I'll pass this to one of our travel specialists, who will get back to you. "
           "Is there anything I can help with in the meantime?")

SLOT_WORDS: dict[Slot, str] = {
    "tour": "which tour you'd like (or what you'd like to see)",
    "start_date": "your start date",
    "adults": "how many adults are travelling",
    "child_ages": "the age of each child",
}
FIRST_QUESTION = "Are you thinking of a day tour, a multi-day tour, or something we'd plan just for you?"


def money(n: int) -> str:
    return f"USD {n:,}"


def nice_date(iso: str | date) -> str:
    d = date.fromisoformat(iso) if isinstance(iso, str) else iso
    return f"{d.day} {d:%B %Y}"


def party_words(adults: int, children: int, infants: int) -> str:
    parts = [f"{adults} adult{'s' * (adults != 1)}"]
    if children:
        parts.append(f"{children} child{'ren' * (children != 1)}")
    if infants:
        parts.append(f"{infants} infant{'s' * (infants != 1)} (free)")
    return ", ".join(parts[:-1]) + (" and " if len(parts) > 1 else "") + parts[-1]


def ask_question(missing: list[Slot]) -> str:
    """One combined question for everything still missing (it counts as one of the three)."""
    words = [SLOT_WORDS[s] for s in missing]
    joined = words[0] if len(words) == 1 else ", ".join(words[:-1]) + " and " + words[-1]
    return f"Could you tell me {joined}?"


def quote_text(q: dict) -> str:
    """The verified quote in fixed wording. Numbers come straight from the PublicQuote."""
    who = party_words(q["adults"], q["children"], q["infants"])
    when = (f"on {nice_date(q['start_date'])}" if q["start_date"] == q["end_date"]
            else f"{nice_date(q['start_date'])} to {nice_date(q['end_date'])}")
    lines = [f"Here is your price for the {q['tour_name']}, {when}, for {who}: "
             f"{money(q['price_usd'])} in total."]
    if q["balance_usd"]:
        lines.append(f"To book, the deposit is {money(q['deposit_usd'])}, and the balance of "
                     f"{money(q['balance_usd'])} is due by {nice_date(q['balance_due'])}.")
    else:
        lines.append(f"The full {money(q['price_usd'])} is paid when you book.")
    return " ".join(lines)


def tour_list(cards: list[dict]) -> str:
    return "\n".join(f"- {c['name']} ({c['why']})" for c in cards)
