"""invoke_structured(): every structured LLM call goes through here (plan §16 step 7).

1. Ask for the schema: Gemini's native JSON-schema output, or function calling for DeepSeek
   (app.llm.client.structured_method).
2. If parsing fails, one repair attempt: show the model its own output and the error.
3. If that fails too, return the caller's SAFE fallback (a handoff, never a quote),
   or raise StructuredOutputError when no fallback was given.

Models are tried in this order: the requested one, then the quick backup
(GEMINI_MODEL_BACKUP / DEEPSEEK_MODEL_BACKUP), then the other main model. A model name already
tried is not tried again (DeepSeek's fast and strong are the same model by default).

Errors (Gemini or DeepSeek) are handled by kind:
- overloaded (503 "high demand") or a dropped connection: retry the same model once after
  1 s, then switch (the second model gets one retry after 2 s);
- timeout (our per-call timeout, or 504 DEADLINE_EXCEEDED): switch to the next model at once.
  Each model has a short timeout (app.llm.client.TIMEOUT_S), so one stuck call can't use up
  the whole turn;
- quota (429): switch to the next model at once (quotas are per model);
- anything else (no key, bad request): switch model, then the fallback.

A model that fails rests (60 s after a quota error, 30 s when overloaded or timing out), so
later calls skip it. Each call has a budget (25 s on Gemini, 50 s on DeepSeek, 55 s on a local
Ollama model, which are slower
per call), and a model is only started if its full timeout still fits in what's left. A chat turn never crashes on an LLM error; at worst it
gets the safe fallback.
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Sequence
from typing import Any, TypeVar

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from pydantic import BaseModel

from app.llm.client import ModelKind, get_chat_model, model_name, provider, structured_method, timeout_for

logger = logging.getLogger("mira.llm")
T = TypeVar("T", bound=BaseModel)

DROPPED_CONNECTION = {"RemoteProtocolError", "ConnectError", "ReadError", "ConnectionResetError",
                      "ConnectionRefusedError",                        # Ollama not running
                      "APIConnectionError", "InternalServerError"}     # the last two: DeepSeek (openai SDK)
TIMEOUT_NAMES = {"ReadTimeout", "ConnectTimeout", "WriteTimeout", "PoolTimeout", "TimeoutException",
                 "TimeoutError", "DeadlineExceeded", "APITimeoutError"}
TIMEOUT_TEXT = ("504", "DEADLINE_EXCEEDED", "Deadline expired", "timed out")
OVERLOADED_TEXT = ("503", "UNAVAILABLE", "high demand", "overloaded", "500 INTERNAL")
QUOTA_TEXT = ("429", "RESOURCE_EXHAUSTED", "quota", "rate limit")
# waits before each RETRY on the same model: one retry on the first and second model, none on
# the third. A busy model rarely recovers within seconds, and the backup is quick to try.
WAITS = ((1.0,), (2.0,), ())
OTHER: dict[str, ModelKind] = {"fast": "strong", "strong": "fast", "backup": "fast"}
_sleep = time.sleep            # tests replace this so they don't wait


class StructuredOutputError(RuntimeError):
    def __init__(self, schema: str, error: Any):
        super().__init__(f"{schema}: {error}")
        self.schema, self.error = schema, error


def error_kind(exc: BaseException) -> str:
    """'overloaded' (retry later), 'timeout' or 'quota' (switch model now) or 'other'."""
    name, text = exc.__class__.__name__, str(exc)
    if "RateLimit" in name or any(t.lower() in text.lower() for t in QUOTA_TEXT):
        return "quota"
    if name in TIMEOUT_NAMES or any(t.lower() in text.lower() for t in TIMEOUT_TEXT):
        return "timeout"
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
    kinds = list(dict.fromkeys([kind, "backup", OTHER[kind]]))     # backup is quick: try it second
    seen: set[str | None] = set()
    chain = []
    for k in kinds:                  # no model set, or the same model again: skip it
        name = _name(k)
        if (name is None and k == "backup") or (name is not None and name in seen):
            continue
        seen.add(name)
        chain.append(_Lazy(k))
    now = _clock()
    ready = [c for c in chain if _resting_until.get(c.kind, 0) <= now]
    return ready or chain            # all resting: try them anyway rather than give up


# A model that just failed sits out for a while, so the next calls go straight to one that
# works instead of waiting through the same errors again (real models only).
REST_SECONDS = {"quota": 60.0, "overloaded": 30.0, "timeout": 30.0}
BUDGET_SECONDS = 25.0          # per call: no retry or model is started that wouldn't fit in it
DEEPSEEK_BUDGET_SECONDS = 50.0 # DeepSeek is slower per call
OLLAMA_BUDGET_SECONDS = 55.0   # a local model: one try of the 50 s limit, then the safe fallback


def _name(kind: ModelKind) -> str | None:
    try:
        return model_name(kind)
    except Exception:  # noqa: BLE001  (settings problem: let get_chat_model report it)
        return kind


def budget_seconds() -> float:
    return {"deepseek": DEEPSEEK_BUDGET_SECONDS, "ollama": OLLAMA_BUDGET_SECONDS}.get(provider(), BUDGET_SECONDS)
_resting_until: dict[str, float] = {}
_clock = time.monotonic


RETRY_DELAY = re.compile(r"retryDelay'?\"?\s*:\s*'?\"?(\d+)(?:\.\d+)?s")
MAX_REST_SECONDS = 3600.0


def rest_seconds(why: str, error: str = "") -> float:
    """How long a failed model sits out. A quota error that says how long to wait (e.g. the
    free tier's daily limit, "retryDelay: 42708s") is honoured, up to an hour."""
    base = REST_SECONDS.get(why, 0.0)
    if why == "quota" and (m := RETRY_DELAY.search(error)):
        return min(max(base, float(m[1])), MAX_REST_SECONDS)
    return base


def _rest(candidate: Any, why: str, error: str = "") -> None:
    if isinstance(candidate, _Lazy) and why in REST_SECONDS:
        _resting_until[candidate.kind] = _clock() + rest_seconds(why, error)


class _Lazy:
    def __init__(self, kind: ModelKind):
        self.kind = kind

    def get(self):
        return get_chat_model(self.kind)

    @property
    def timeout(self) -> float:
        return timeout_for(self.kind)


def invoke_structured(schema: type[T], messages: Sequence[BaseMessage], *, kind: ModelKind = "fast",
                      fallback: T | None = None, model: Any = None, config: dict | None = None) -> T:
    """Return a validated `schema` object, the fallback, or raise. `model` is for tests."""
    messages = list(messages)
    error: Any = None
    repaired = False
    deadline = _clock() + (budget_seconds() if model is None else BUDGET_SECONDS)
    for i, candidate in enumerate(_models(model, kind)):
        # out of time: a quick safe reply beats a long wait. A real model must have room for
        # its whole timeout; a test fake (no timeout) only needs the budget not to be over.
        if i and _clock() + getattr(candidate, "timeout", 0.0) > deadline:
            break
        waits = list(WAITS[min(i, len(WAITS) - 1)])
        try:
            m = candidate.get() if isinstance(candidate, _Lazy) else candidate
            method = structured_method() if isinstance(candidate, _Lazy) else "json_schema"
            runnable = m.with_structured_output(schema, method=method, include_raw=True)
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
                room = _clock() + (waits[0] if waits else 0) + getattr(candidate, "timeout", 0.0)
                if why == "overloaded" and waits and room <= deadline:
                    _sleep(waits.pop(0))
                    continue
                _rest(candidate, why, str(exc))
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
