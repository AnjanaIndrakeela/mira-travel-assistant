"""Langfuse tracing for chat turns (steps 8.15-8.17).

- One trace per turn, grouped into a session per conversation (thread_id).
- The LangChain callback records every graph node (guard, retrieve, price, build_ui, ...) as a
  span and every Gemini call as a generation, with token usage.
- mask_trace() redacts emails, phone numbers, card-like and passport-like numbers in
  everything sent to Langfuse (inputs, outputs, metadata).
- Tracing is optional and can never break a chat: no keys, a wrong key, or Langfuse being down
  only means no trace. Export runs in a background thread.
"""

from __future__ import annotations

import logging
from contextlib import ExitStack
from functools import lru_cache
from typing import Any

from langchain_core.messages import HumanMessage

from app.core.config import Settings, get_settings
from app.graph.prompts import PROMPT_VERSION
from app.guards.input_guard import mask_personal_data

logger = logging.getLogger("mira.tracing")


def mask_trace(*, data: Any, **_: Any) -> Any:
    """Langfuse mask hook: redact personal data in any string, however deeply nested."""
    if isinstance(data, str):
        return mask_personal_data(data)
    if isinstance(data, dict):
        return {k: mask_trace(data=v) for k, v in data.items()}
    if isinstance(data, (list, tuple)):
        return [mask_trace(data=v) for v in data]
    return data


@lru_cache
def get_langfuse():
    """The app's Langfuse client, or None when tracing is off or can't start."""
    return make_langfuse(get_settings())


def make_langfuse(settings: Settings):
    if not settings.tracing_enabled:
        return None
    try:
        from langfuse import Langfuse
        return Langfuse(public_key=settings.langfuse_public_key, secret_key=settings.langfuse_secret_key,
                        host=settings.langfuse_host, mask=mask_trace)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Langfuse disabled: %s", exc.__class__.__name__)
        return None


def run_turn(graph, thread_id: str, message: str, *, visitor_id: str | None = None,
             langfuse=None, flush: bool = False) -> dict:
    """Run one chat turn through the graph, traced when Langfuse is available."""
    lf = langfuse if langfuse is not None else get_langfuse()
    config: dict = {"configurable": {"thread_id": thread_id}, "run_name": "mira-turn"}
    turn_input = {"messages": [HumanMessage(content=message)], "thread_id": thread_id,
                  "visitor_id": visitor_id, "trace_id": None}
    with ExitStack() as stack:
        span = None
        if lf is not None:
            try:
                from langfuse import propagate_attributes
                from langfuse.langchain import CallbackHandler
                span = stack.enter_context(lf.start_as_current_observation(
                    name="mira-turn", as_type="agent", input=mask_personal_data(message)))
                stack.enter_context(propagate_attributes(
                    session_id=thread_id, user_id=visitor_id, trace_name="mira-turn",
                    metadata={"prompt_version": PROMPT_VERSION}))
                config["callbacks"] = [CallbackHandler()]
                turn_input["trace_id"] = lf.get_current_trace_id()
            except Exception as exc:  # noqa: BLE001  (8.17: tracing problems never stop a reply)
                logger.warning("tracing setup failed: %s", exc.__class__.__name__)
                config.pop("callbacks", None)
        result = graph.invoke(turn_input, config)
        if span is not None:
            try:
                span.update(output=result.get("response"),
                            metadata={"action": result.get("action"), "flags": result.get("flags"),
                                      "intent": result.get("intent")})
            except Exception:  # noqa: BLE001
                pass
    if lf is not None and flush:
        try:
            lf.flush()
        except Exception:  # noqa: BLE001
            pass
    return result
