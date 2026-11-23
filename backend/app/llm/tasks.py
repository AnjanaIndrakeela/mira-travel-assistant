"""The small LLM tasks the graph needs before any answer: route and extract.

The graph calls analyse_turn() (both in one call); route_message() and extract_trip() remain
for focused tests.

Both have SAFE fallbacks: if Gemini fails or returns junk twice, routing becomes a handoff
(never a quote) and extraction returns "nothing known yet" (so Mira asks, never guesses).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from app.graph.prompts import load_prompt
from app.llm.schemas import Intent, RouterDecision, TripDetails, TurnAnalysis
from app.llm.structured import invoke_structured

ROUTER_FALLBACK = RouterDecision(intent=Intent.HANDOFF, needs_retrieval=False)
EXTRACT_FALLBACK = TripDetails(missing=["tour", "start_date", "adults"])
COMPANY = "Ceylon Compass Holidays"


def transcript(history: Sequence[BaseMessage], last: int = 10) -> str:
    lines = []
    for m in list(history)[-last:]:
        who = "traveller" if m.type == "human" else "assistant"
        lines.append(f"{who}: {m.text if isinstance(m.text, str) else m.content}")
    return "\n".join(lines)


def route_message(message: str, history: Sequence[BaseMessage] = (), *, model=None,
                  config: dict | None = None) -> RouterDecision:
    msgs = [SystemMessage(content="You classify messages for a travel assistant. Reply only with JSON."),
            *list(history)[-6:],
            HumanMessage(content=load_prompt("router", company=COMPANY, message=message))]
    return invoke_structured(RouterDecision, msgs, fallback=ROUTER_FALLBACK, model=model, config=config)


ANALYSIS_FALLBACK = TurnAnalysis(intent=Intent.HANDOFF, needs_retrieval=False, trip=EXTRACT_FALLBACK)


def analyse_turn(message: str, history: Sequence[BaseMessage], today: date, *, model=None,
                 config: dict | None = None) -> TurnAnalysis:
    """Route and extract in one call: what the graph uses on every turn."""
    msgs = [SystemMessage(content="You analyse messages for a travel assistant. Reply only with JSON."),
            HumanMessage(content=load_prompt("analyse_turn", company=COMPANY, today=today.isoformat(),
                                             conversation=transcript(history) or "(none yet)",
                                             message=message))]
    return invoke_structured(TurnAnalysis, msgs, fallback=ANALYSIS_FALLBACK, model=model, config=config)


def extract_trip(history: Sequence[BaseMessage], today: date, *, model=None,
                 config: dict | None = None) -> TripDetails:
    msgs = [SystemMessage(content="You extract trip details for a travel assistant. Reply only with JSON."),
            HumanMessage(content=load_prompt("extract_trip", today=today.isoformat(),
                                             conversation=transcript(history)))]
    return invoke_structured(TripDetails, msgs, fallback=EXTRACT_FALLBACK, model=model, config=config)
