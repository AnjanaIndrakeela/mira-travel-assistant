"""One place that creates the chat models (plan §16 step 1).

Provider: DeepSeek when DEEPSEEK_API_KEY is set (LLM_PROVIDER=auto, the default), else Gemini.
LLM_PROVIDER=deepseek, =gemini or =ollama forces one; Ollama (a local model, no key) is only
used when chosen. Embeddings (search) always use Gemini, in app.rag.embeddings.

- fast  = routing, extraction and most answers
- strong = only where it measurably helps
- backup = a different model tried when the main ones fail (optional)
temperature 0 so the same question gives the same answer; evals depend on it.

Structured output: Gemini and Ollama use a JSON-schema mode (Ollama constrains the output to
the schema); DeepSeek has none, so it uses function calling (the schema becomes a tool).
"""

from __future__ import annotations

import warnings
from functools import lru_cache
from typing import Any, Literal

from langchain_core.messages import BaseMessage

from app.core.config import get_settings

# Some models (e.g. the backup) ignore temperature and warn on every call; that is expected.
warnings.filterwarnings("ignore", message=".*uses fixed sampling defaults.*")

ModelKind = Literal["fast", "strong", "backup"]
Provider = Literal["deepseek", "gemini", "ollama"]
THINKING: dict[str, str] = {"fast": "minimal", "strong": "low", "backup": "minimal"}
MODEL_SETTING: dict[str, dict[str, str]] = {
    "gemini": {"fast": "gemini_model_fast", "strong": "gemini_model_strong", "backup": "gemini_model_backup"},
    "deepseek": {"fast": "deepseek_model_fast", "strong": "deepseek_model_strong",
                 "backup": "deepseek_model_backup"},
    "ollama": {"fast": "ollama_model_fast", "strong": "ollama_model_strong", "backup": "ollama_model_backup"},
}
# Per-call timeouts (seconds). A stuck call gives up early so app.llm.structured can switch
# model (or fall back) in time.
# Gemini: a healthy call takes 1-6 s, and Gemini refuses deadlines under 10 s
# ("Minimum allowed deadline is 10s", checked 2026-11-24).
MIN_DEADLINE_S = 10.0
TIMEOUT_S: dict[str, float] = {"fast": 10.0, "strong": 15.0, "backup": 10.0}
# DeepSeek: slower per call (no "minimal thinking" setting), so longer limits.
DEEPSEEK_TIMEOUT_S: dict[str, float] = {"fast": 20.0, "strong": 30.0, "backup": 20.0}
# Ollama on a laptop GPU: the first call loads the model, and a long reply is slow. Two calls a
# turn must still fit the chat page's 120 s wait.
OLLAMA_TIMEOUT_S: dict[str, float] = {"fast": 50.0, "strong": 50.0, "backup": 50.0}
TIMEOUTS: dict[str, dict[str, float]] = {"gemini": TIMEOUT_S, "deepseek": DEEPSEEK_TIMEOUT_S,
                                         "ollama": OLLAMA_TIMEOUT_S}


class LLMNotConfigured(RuntimeError):
    """No API key (or no model name) for the chosen provider."""


def provider() -> Provider:
    s = get_settings()
    if s.llm_provider != "auto":
        return s.llm_provider
    return "deepseek" if s.deepseek_api_key is not None else "gemini"


def llm_configured() -> bool:
    s = get_settings()
    p = provider()
    if p == "ollama":
        return bool(s.ollama_base_url and s.ollama_model_fast)        # no key; may still be offline
    return (s.deepseek_api_key if p == "deepseek" else s.gemini_api_key) is not None


def model_name(kind: ModelKind) -> str | None:
    return getattr(get_settings(), MODEL_SETTING[provider()][kind]) or None


def timeout_for(kind: ModelKind) -> float:
    return TIMEOUTS[provider()][kind]


def structured_method() -> str:
    return "function_calling" if provider() == "deepseek" else "json_schema"


@lru_cache
def get_chat_model(kind: ModelKind = "fast") -> Any:
    s = get_settings()
    name = model_name(kind)
    if not name:
        raise LLMNotConfigured(f"no {kind} model is set")
    if provider() == "ollama":
        from langchain_ollama import ChatOllama
        return ChatOllama(
            model=name,
            base_url=s.ollama_base_url,
            temperature=0,
            reasoning=False,          # no "thinking" text: faster, and the JSON stays clean
            num_ctx=s.ollama_num_ctx,
            keep_alive=s.ollama_keep_alive,
            client_kwargs={"timeout": OLLAMA_TIMEOUT_S[kind]},
        )
    if provider() == "deepseek":
        if s.deepseek_api_key is None:
            raise LLMNotConfigured("DEEPSEEK_API_KEY is not set")
        from langchain_deepseek import ChatDeepSeek
        return ChatDeepSeek(
            model=name,
            api_key=s.deepseek_api_key.get_secret_value(),
            api_base=s.deepseek_base_url,
            temperature=0,
            max_retries=1,      # app.llm.structured does the backoff and the fallback
            timeout=DEEPSEEK_TIMEOUT_S[kind],
        )
    if s.gemini_api_key is None:
        raise LLMNotConfigured("GEMINI_API_KEY is not set")
    from langchain_google_genai import ChatGoogleGenerativeAI
    return ChatGoogleGenerativeAI(
        model=name,
        google_api_key=s.gemini_api_key.get_secret_value(),
        temperature=0,
        max_retries=1,      # app.llm.structured does the backoff and the model switch
        timeout=TIMEOUT_S[kind],
        thinking_config={"thinking_level": THINKING[kind]},
    )


def text_of(message: BaseMessage) -> str:
    """Gemini 3 replies are a list of parts; DeepSeek's are plain text. This returns the text."""
    return message.text if isinstance(message.text, str) else str(message.content)
