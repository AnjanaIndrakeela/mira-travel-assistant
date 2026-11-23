"""One place that creates Gemini chat models (plan §16 step 1).

- fast  = routing, extraction and most answers (thinking "minimal": low latency)
- strong = only where it measurably helps (thinking "low")
temperature 0 so the same question gives the same answer; evals depend on it.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from langchain_core.messages import BaseMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from app.core.config import get_settings

ModelKind = Literal["fast", "strong"]
THINKING: dict[str, str] = {"fast": "minimal", "strong": "low"}


class LLMNotConfigured(RuntimeError):
    """GEMINI_API_KEY is not set."""


@lru_cache
def get_chat_model(kind: ModelKind = "fast") -> ChatGoogleGenerativeAI:
    s = get_settings()
    if s.gemini_api_key is None:
        raise LLMNotConfigured("GEMINI_API_KEY is not set")
    return ChatGoogleGenerativeAI(
        model=s.gemini_model_fast if kind == "fast" else s.gemini_model_strong,
        google_api_key=s.gemini_api_key.get_secret_value(),
        temperature=0,
        max_retries=2,
        timeout=30,
        thinking_config={"thinking_level": THINKING[kind]},
    )


def text_of(message: BaseMessage) -> str:
    """Gemini 3 replies are a list of parts; this returns just the text."""
    return message.text if isinstance(message.text, str) else str(message.content)
