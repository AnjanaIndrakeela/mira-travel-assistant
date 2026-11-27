"""Langfuse tracing for chat turns and staff content drafts (steps 8.15-8.17).

- One trace per chat turn (`mira-turn`), grouped into a session per conversation (thread_id),
  tagged `chat`; one trace per staff draft (`write-tour-draft`), tagged `content-writer`.
- The LangChain callback records every graph node as an observation of the right type
  (guard = guardrail, retrieve/match_tours = retriever, price = tool, plan_trip = agent, ...)
  and every Gemini call as a named generation (`analyse-turn-generation`, ...) with model,
  token usage and cost. LangChain plumbing (output parsers, edge functions) is not exported.
- Every trace carries the environment, the prompt version and, when set, the release.
- mask_trace() redacts emails, phone numbers, card-like and passport-like numbers in
  everything sent to Langfuse (inputs, outputs, metadata).
- Tracing is optional and can never break a chat: no keys, a wrong key, or Langfuse being down
  only means no trace. Export runs in a background thread.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from langchain_core.messages import HumanMessage

from app.core.config import Settings, get_settings
from app.graph.prompts import PROMPT_VERSION
from app.guards.input_guard import mask_personal_data

logger = logging.getLogger("mira.tracing")

TURN_TRACE = "mira-turn"
GRAPH_RUN = "chat-graph"          # the LangGraph run under the turn's root (not a second "mira-turn")

# Graph node -> Langfuse observation type (anything else stays a chain).
NODE_TYPES = {
    "guard": "guardrail",          # injection / personal-data checks + the turn analysis
    "retrieve": "retriever",       # RAG over the published pages
    "match_tours": "retriever",    # tour search for open questions
    "price": "tool",               # the deterministic price calculator
    "plan_trip": "agent",          # the trip-planner sub-agent
    "validate": "guardrail",       # content writer: checks the draft against the sources
}

# LangChain plumbing that adds rows but no information. Each of these is a leaf or a subtree
# made only of these names (the structured-output parsing branch), so dropping them never
# orphans an observation that is kept. The parsed result is still the output of the named
# chain above them (e.g. `analyse-turn`).
_NOISE_NAMES = {"RunnableWithFallbacks", "RunnableLambda", "PydanticOutputParser",
                "JsonOutputParser", "RunnableSequence"}
_NOISE_PREFIXES = ("RunnableAssign<", "RunnableParallel<parsed", "_after_")


def mask_trace(*, data: Any, **_: Any) -> Any:
    """Langfuse mask hook: redact personal data in any string, however deeply nested."""
    if isinstance(data, str):
        return mask_personal_data(data)
    if isinstance(data, dict):
        return {k: mask_trace(data=v) for k, v in data.items()}
    if isinstance(data, (list, tuple)):
        return [mask_trace(data=v) for v in data]
    return data


def is_noise(name: str | None) -> bool:
    return bool(name) and (name in _NOISE_NAMES or name.startswith(_NOISE_PREFIXES))


def export_span(span) -> bool:
    """Langfuse should_export_span hook: the SDK's default filter, minus LangChain plumbing."""
    from langfuse.span_filter import is_default_export_span
    return is_default_export_span(span) and not is_noise(getattr(span, "name", None))


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
                        host=settings.langfuse_host, mask=mask_trace, should_export_span=export_span,
                        environment=settings.langfuse_tracing_environment,
                        release=settings.langfuse_release or None)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Langfuse disabled: %s", exc.__class__.__name__)
        return None


@lru_cache
def _handler_class():
    from langfuse.langchain import CallbackHandler

    class TypedCallbackHandler(CallbackHandler):
        """Gives graph nodes their real observation type (see NODE_TYPES)."""

        def _get_observation_type_from_serialized(self, serialized, callback_type, **kwargs):
            if callback_type == "chain" and (kind := NODE_TYPES.get(kwargs.get("name") or "")):
                return kind
            return super()._get_observation_type_from_serialized(serialized, callback_type, **kwargs)

    return TypedCallbackHandler


@dataclass
class Traced:
    """What observe() hands back: callbacks for the LangChain config, the root, the trace id."""
    callbacks: list = field(default_factory=list)
    span: Any = None
    trace_id: str | None = None

    def finish(self, output: Any = None, metadata: dict | None = None, *,
               error: str | None = None) -> None:
        """Set the root's output; `error` marks the whole run as failed (level ERROR), so
        failed runs can be filtered in Langfuse without opening each trace."""
        if self.span is None:
            return
        try:
            extra = {"level": "ERROR", "status_message": error} if error else {}
            self.span.update(output=output, metadata=metadata, **extra)
        except Exception:  # noqa: BLE001
            pass


@contextmanager
def observe(name: str, *, input: Any, tags: list[str], as_type: str = "agent",
            session_id: str | None = None, user_id: str | None = None,
            metadata: dict | None = None, langfuse=None, flush: bool = False) -> Iterator[Traced]:
    """One traced run: an `as_type` root called `name` (also the trace name) with only the
    relevant input, and trace-wide session, user, tags and metadata. Never raises because of
    Langfuse: on any tracing problem the run goes ahead untraced."""
    lf = langfuse if langfuse is not None else get_langfuse()
    traced = Traced()
    with ExitStack() as stack:
        if lf is not None:
            try:
                from langfuse import propagate_attributes
                traced.span = stack.enter_context(lf.start_as_current_observation(
                    name=name, as_type=as_type, input=input))
                stack.enter_context(propagate_attributes(
                    session_id=session_id, user_id=user_id, trace_name=name, tags=tags,
                    version=PROMPT_VERSION,
                    metadata={"prompt_version": PROMPT_VERSION, **(metadata or {})}))
                traced.callbacks = [_handler_class()()]
                traced.trace_id = lf.get_current_trace_id()
            except Exception as exc:  # noqa: BLE001  (8.17: tracing problems never stop a reply)
                logger.warning("tracing setup failed: %s", exc.__class__.__name__)
                traced.callbacks = []
        yield traced
    if lf is not None and flush:
        try:
            lf.flush()
        except Exception:  # noqa: BLE001
            pass


def run_turn(graph, thread_id: str, message: str, *, visitor_id: str | None = None,
             conversation_id: str | None = None,
             langfuse=None, flush: bool = False,
             on_step: Callable[[str], None] | None = None) -> dict:
    """Run one chat turn through the graph, traced when Langfuse is available.
    on_step(node_name) is called after each node finishes (used by the SSE stream)."""
    config: dict = {"configurable": {"thread_id": thread_id}, "run_name": GRAPH_RUN}
    turn_input = {"messages": [HumanMessage(content=message)], "thread_id": thread_id,
                  "conversation_id": conversation_id,
                  "visitor_id": visitor_id, "trace_id": None}
    with observe(TURN_TRACE, input=mask_personal_data(message), tags=["chat"],
                 session_id=thread_id, user_id=visitor_id,
                 metadata={"conversation_id": conversation_id} if conversation_id else None,
                 langfuse=langfuse, flush=flush) as traced:
        if traced.callbacks:
            config["callbacks"] = traced.callbacks
        turn_input["trace_id"] = traced.trace_id
        if on_step is None:
            result = graph.invoke(turn_input, config)
        else:   # same run, node by node, so a stream can show progress (11.1)
            for update in graph.stream(turn_input, config, stream_mode="updates"):
                for node in update:
                    try:
                        on_step(node)
                    except Exception:  # noqa: BLE001  (a slow or gone client never breaks a turn)
                        pass
            result = graph.get_state({"configurable": {"thread_id": thread_id}}).values
        traced.finish(output=result.get("response"),
                      metadata={"action": result.get("action"), "flags": result.get("flags"),
                                "intent": result.get("intent")})
    return result
