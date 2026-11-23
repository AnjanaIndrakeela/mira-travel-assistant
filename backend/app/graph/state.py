"""The state that flows through Mira's graph (plan §6.1).

One MiraState per conversation thread, kept by the checkpointer between turns. `messages`
is appended to (add_messages); every other key is overwritten by the node that returns it.
Per-turn keys (retrieved, quote, ui, response, ...) are reset by the guard at the start of
each turn so nothing from the last turn leaks into this one.

Prices: `quote` is a PublicQuote dump (no cost fields ever). The StaffQuote never enters
the state, so it can't reach the LLM, the UI or the checkpointer; `persist` recomputes and
stores it (Phase 9).
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

TravellerType = Literal["solo", "couple", "family", "group"]
TripType = Literal["day", "multi_day", "custom"]
Action = Literal["greet", "ask", "price", "match_tours", "retrieve", "decline", "off_topic", "handoff"]
Slot = Literal["tour", "start_date", "adults", "child_ages"]


class Party(TypedDict):
    adults: int
    child_ages: list[int]


class TourCard(TypedDict):
    tour_id: str
    name: str
    duration: str
    destinations: list[str]
    why: str


class MiraState(TypedDict, total=False):
    # conversation
    messages: Annotated[list[AnyMessage], add_messages]
    thread_id: str
    visitor_id: str | None
    is_returning: bool
    turn: int

    # this turn's classification
    intent: str
    needs_retrieval: bool
    input_flags: list[str]

    # what we know about the trip (kept across turns; newer values win)
    trip_type: TripType | None
    traveller_type: TravellerType | None
    party: Party | None
    start_date: str | None            # ISO date; strings keep the checkpoint JSON-friendly
    travel_month: int | None
    selected_tour_id: str | None
    tour_mention: str | None          # as the traveller wrote it, when it matched nothing
    destinations: list[str]
    interests: list[str]
    duration_days: int | None
    suggested_tour_ids: list[str]     # tour cards shown earlier, for "yes, that one"
    children_without_age: bool        # a child was mentioned but not their age
    questions_asked: int              # toward the limit of 3 (R1)

    # this turn's work
    tour_mention: str | None          # what the router saw named in THIS message
    unmatched_tour: str | None        # named in this message but not in our published catalogue
    trip: dict[str, Any] | None       # TripDetails the guard's Gemini call extracted this turn
    slots_changed: bool               # this message added or changed tour/date/party
    assumed_tour: bool                # priced the top suggestion because no tour was named
    question: str | None              # the one question code decided to ask, if any
    action: Action
    missing: list[Slot]
    retrieved: list[dict[str, Any]]   # RetrievedChunk dumps, numbered [1].. in this order
    abstain_reason: str | None
    tour_cards: list[TourCard]
    quote: dict[str, Any] | None      # PublicQuote dump (JSON mode)
    quote_request: dict[str, Any] | None
    refusals: list[dict[str, str]]    # {code, message} - traveller-safe messages only
    quote_id: str | None
    enquiry_id: str | None
    flags: list[str]                  # staff flags for this turn (no_price, custom_request, injection...)
    response: str
    ui: list[dict[str, Any]]
    citations: list[int]
    trace_id: str | None


# Keys cleared at the start of every turn (the guard returns these defaults).
PER_TURN_DEFAULTS: dict[str, Any] = {
    "intent": "", "needs_retrieval": False, "input_flags": [], "tour_mention": None, "trip": None,
    "unmatched_tour": None, "slots_changed": False, "assumed_tour": False, "question": None,
    "action": "handoff", "missing": [],
    "retrieved": [], "abstain_reason": None, "tour_cards": [], "quote": None, "quote_request": None,
    "refusals": [], "quote_id": None, "enquiry_id": None, "flags": [], "response": "", "ui": [],
    "citations": [],
}   # trace_id is not reset: the caller sets it in each turn's input (None without tracing)
