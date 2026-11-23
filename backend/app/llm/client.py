"""One place that creates Gemini chat models (plan §16 step 1).

- fast  = routing, extraction and most answers (thinking "minimal": low latency)
- strong = only where it measurably helps (thinking "low")
temperature 0 so the same question gives the same answer; evals depend on it.
"""

from __future__ import annotations

import warnings
from functools import lru_cache
from typing import Literal

from langchain_core.messages import BaseMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from app.core.config import get_settings

# Some models (e.g. the backup) ignore temperature and warn on every call; that is expected.
warnings.filterwarnings("ignore", message=".*uses fixed sampling defaults.*")

ModelKind = Literal["fast", "strong", "backup"]
THINKING: dict[str, str] = {"fast": "minimal", "strong": "low", "backup": "minimal"}
MODEL_SETTING = {"fast": "gemini_model_fast", "strong": "gemini_model_strong", "backup": "gemini_model_backup"}
# Per-call timeouts (seconds), also sent to Gemini as the request deadline. A healthy call takes
# 1-6 s; a stuck one gives up early so app.llm.structured can switch to another model in time.
# Gemini refuses deadlines under 10 s ("Minimum allowed deadline is 10s", checked 2026-11-24).
MIN_DEADLINE_S = 10.0
TIMEOUT_S: dict[str, float] = {"fast": 10.0, "strong": 15.0, "backup": 10.0}


class LLMNotConfigured(RuntimeError):
    """GEMINI_API_KEY is not set."""


@lru_cache
def get_chat_model(kind: ModelKind = "fast") -> ChatGoogleGenerativeAI:
    s = get_settings()
    if s.gemini_api_key is None:
        raise LLMNotConfigured("GEMINI_API_KEY is not set")
    name = getattr(s, MODEL_SETTING[kind])
    if not name:
        raise LLMNotConfigured(f"no {kind} model is set")
    return ChatGoogleGenerativeAI(
        model=name,
        google_api_key=s.gemini_api_key.get_secret_value(),
        temperature=0,
        max_retries=1,      # app.llm.structured does the backoff and the model switch
        timeout=TIMEOUT_S[kind],
        thinking_config={"thinking_level": THINKING[kind]},
    )


def text_of(message: BaseMessage) -> str:
    """Gemini 3 replies are a list of parts; this returns just the text."""
    return message.text if isinstance(message.text, str) else str(message.content)
