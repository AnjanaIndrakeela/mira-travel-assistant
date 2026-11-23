"""invoke_structured(): every structured LLM call goes through here (plan §16 step 7).

1. Ask for the schema with Gemini's native JSON-schema output.
2. If parsing fails, one repair attempt: show the model its own output and the error.
3. If that fails too, return the caller's SAFE fallback (a handoff, never a quote),
   or raise StructuredOutputError when no fallback was given.
A network or API error is treated like a failed parse: fallback, never a crash mid-chat.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any, TypeVar

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from pydantic import BaseModel

from app.llm.client import ModelKind, get_chat_model

logger = logging.getLogger("mira.llm")
T = TypeVar("T", bound=BaseModel)


class StructuredOutputError(RuntimeError):
    def __init__(self, schema: str, error: Any):
        super().__init__(f"{schema}: {error}")
        self.schema, self.error = schema, error


def _raw_text(raw: Any) -> str:
    if raw is None:
        return ""
    text = getattr(raw, "text", None)
    return text if isinstance(text, str) else str(getattr(raw, "content", raw))


def invoke_structured(schema: type[T], messages: Sequence[BaseMessage], *, kind: ModelKind = "fast",
                      fallback: T | None = None, model: Any = None, config: dict | None = None) -> T:
    """Return a validated `schema` object, the fallback, or raise. `model` is for tests."""
    runnable = (model or get_chat_model(kind)).with_structured_output(
        schema, method="json_schema", include_raw=True)
    messages = list(messages)
    error: Any = None
    for attempt in range(2):
        try:
            out = runnable.invoke(messages, config=config)
        except Exception as exc:  # noqa: BLE001  (API down, timeout, quota)
            error = f"{exc.__class__.__name__}: {exc}"
            logger.warning("structured call for %s failed: %s", schema.__name__, exc.__class__.__name__)
            break
        parsed = out.get("parsed")
        if isinstance(parsed, schema):
            return parsed
        if isinstance(parsed, dict):
            try:
                return schema.model_validate(parsed)
            except Exception as exc:  # noqa: BLE001
                out["parsing_error"] = exc
        error = out.get("parsing_error") or "no parsed output"
        if attempt == 0:
            messages = messages + [
                AIMessage(content=_raw_text(out.get("raw")) or "(empty)"),
                HumanMessage(content=f"That reply did not match the required JSON schema: {error}. "
                                     "Reply again with only valid JSON for the schema."),
            ]
    if fallback is not None:
        logger.warning("structured output for %s fell back: %s", schema.__name__, error)
        return fallback
    raise StructuredOutputError(schema.__name__, error)
