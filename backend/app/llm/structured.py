"""invoke_structured(): every structured LLM call goes through here (plan §16 step 7).

1. Ask for the schema with Gemini's native JSON-schema output.
2. If parsing fails, one repair attempt: show the model its own output and the error.
3. If that fails too, return the caller's SAFE fallback (a handoff, never a quote),
   or raise StructuredOutputError when no fallback was given.

Gemini errors are handled by kind:
- overloaded (503 "high demand"), timeout or dropped connection: wait and retry the same
  model (1 s, then 2 s), then switch to the other model (one retry after 4 s), then try
  the backup model once (GEMINI_MODEL_BACKUP);
- quota (429): switch to the next model at once (quotas are per model);
- anything else (no key, bad request): switch model, then the fallback.
A model that fails rests (60 s after a quota error, 30 s when overloaded), so later calls skip
it. Each call stops starting new retries after 25 s. A chat turn never crashes on an LLM
error; at worst it gets the safe fallback.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Sequence
from typing import Any, TypeVar

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from pydantic import BaseModel

from app.llm.client import ModelKind, get_chat_model

logger = logging.getLogger("mira.llm")
T = TypeVar("T", bound=BaseModel)

DROPPED_CONNECTION = {"RemoteProtocolError", "ConnectError", "ReadError", "ConnectionResetError",
                      "ReadTimeout", "ConnectTimeout", "TimeoutException", "TimeoutError"}
OVERLOADED_TEXT = ("503", "UNAVAILABLE", "high demand", "overloaded", "504", "DEADLINE_EXCEEDED",
                   "500 INTERNAL")
QUOTA_TEXT = ("429", "RESOURCE_EXHAUSTED", "quota", "rate limit")
# waits before each RETRY on the same model: first model 2 retries, second 1, backup none
WAITS = ((1.0, 2.0), (4.0,), ())
OTHER: dict[str, ModelKind] = {"fast": "strong", "strong": "fast", "backup": "fast"}
_sleep = time.sleep            # tests replace this so they don't wait


class StructuredOutputError(RuntimeError):
    def __init__(self, schema: str, error: Any):
        super().__init__(f"{schema}: {error}")
        self.schema, self.error = schema, error


def error_kind(exc: BaseException) -> str:
    """'overloaded' (retry later), 'quota' (switch model now) or 'other'."""
    name, text = exc.__class__.__name__, str(exc)
    if "RateLimit" in name or any(t.lower() in text.lower() for t in QUOTA_TEXT):
        return "quota"
    if name in DROPPED_CONNECTION or any(t.lower() in text.lower() for t in OVERLOADED_TEXT):
        return "overloaded"
    return "other"


def _raw_text(raw: Any) -> str:
    if raw is None:
        return ""
    text = getattr(raw, "text", None)
    return text if isinstance(text, str) else str(getattr(raw, "content", raw))


def _models(model: Any, kind: ModelKind) -> list[Any]:
    """The models to try in order. `model` (tests) may be one fake or a list of fakes.
    Real models are created lazily, so a missing key is an error like any other."""
    if model is not None:
        return list(model) if isinstance(model, (list, tuple)) else [model]
    chain = [_Lazy(kind), _Lazy(OTHER[kind]), _Lazy("backup")]
    now = _clock()
    ready = [c for c in chain if _resting_until.get(c.kind, 0) <= now]
    return ready or chain            # all resting: try them anyway rather than give up


# A model that just failed sits out for a while, so the next calls go straight to one that
# works instead of waiting through the same errors again (real models only).
REST_SECONDS = {"quota": 60.0, "overloaded": 30.0}
BUDGET_SECONDS = 25.0          # per call: no new retry or model once this has passed
_resting_until: dict[str, float] = {}
_clock = time.monotonic


def _rest(candidate: Any, why: str) -> None:
    if isinstance(candidate, _Lazy) and why in REST_SECONDS:
        _resting_until[candidate.kind] = _clock() + REST_SECONDS[why]


class _Lazy:
    def __init__(self, kind: ModelKind):
        self.kind = kind

    def get(self):
        return get_chat_model(self.kind)


def invoke_structured(schema: type[T], messages: Sequence[BaseMessage], *, kind: ModelKind = "fast",
                      fallback: T | None = None, model: Any = None, config: dict | None = None) -> T:
    """Return a validated `schema` object, the fallback, or raise. `model` is for tests."""
    messages = list(messages)
    error: Any = None
    repaired = False
    deadline = _clock() + BUDGET_SECONDS
    for i, candidate in enumerate(_models(model, kind)):
        if i and _clock() > deadline:
            break                     # out of time: a quick safe reply beats a long wait
        waits = list(WAITS[min(i, len(WAITS) - 1)])
        try:
            m = candidate.get() if isinstance(candidate, _Lazy) else candidate
            runnable = m.with_structured_output(schema, method="json_schema", include_raw=True)
        except Exception as exc:  # noqa: BLE001  (no key)
            error = f"{exc.__class__.__name__}: {exc}"
            continue
        while True:
            try:
                out = runnable.invoke(messages, config=config)
            except Exception as exc:  # noqa: BLE001  (API down, timeout, quota)
                error = f"{exc.__class__.__name__}: {exc}"
                why = error_kind(exc)
                logger.warning("structured call for %s failed (%s, model %d): %s",
                               schema.__name__, why, i + 1, exc.__class__.__name__)
                if why == "overloaded" and waits and _clock() + waits[0] < deadline:
                    _sleep(waits.pop(0))
                    continue
                _rest(candidate, why)
                break                                       # next model
            if isinstance(candidate, _Lazy):
                _resting_until.pop(candidate.kind, None)       # it works again
            parsed = out.get("parsed")
            if isinstance(parsed, schema):
                return parsed
            if isinstance(parsed, dict):
                try:
                    return schema.model_validate(parsed)
                except Exception as exc:  # noqa: BLE001
                    out["parsing_error"] = exc
            error = out.get("parsing_error") or "no parsed output"
            if repaired:
                return _give_up(schema, fallback, error)    # bad output twice: stop
            repaired = True
            messages = messages + [
                AIMessage(content=_raw_text(out.get("raw")) or "(empty)"),
                HumanMessage(content=f"That reply did not match the required JSON schema: {error}. "
                                     "Reply again with only valid JSON for the schema."),
            ]
    return _give_up(schema, fallback, error)


def _give_up(schema: type[T], fallback: T | None, error: Any) -> T:
    if fallback is not None:
        logger.warning("structured output for %s fell back: %s", schema.__name__, error)
        return fallback
    raise StructuredOutputError(schema.__name__, error)
