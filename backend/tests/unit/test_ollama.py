"""Ollama (a local model) as the chat provider: only when chosen, JSON-schema output, its own
time limits, and a stopped Ollama still gives the safe fallback. Offline: no model is called."""

import pytest

from app.core.config import Settings
from app.llm import client, structured
from app.llm.schemas import Intent, RouterDecision

pytestmark = pytest.mark.deepseek          # sees the real provider choice (see conftest)
SAFE = RouterDecision(intent=Intent.HANDOFF, needs_retrieval=False)


@pytest.fixture
def use_settings(monkeypatch):
    def apply(**kw):
        kw.setdefault("llm_provider", "auto")      # not whatever LLM_PROVIDER the machine has
        s = Settings(_env_file=None, **kw)
        monkeypatch.setattr(client, "get_settings", lambda: s)
        client.get_chat_model.cache_clear()
        return s
    yield apply
    client.get_chat_model.cache_clear()


def test_ollama_is_only_used_when_chosen(use_settings):
    use_settings(gemini_api_key="g")
    assert client.provider() == "gemini"                     # auto never picks a local model
    use_settings(llm_provider="ollama")
    assert client.provider() == "ollama" and client.llm_configured()      # no key needed


def test_ollama_model_settings(use_settings):
    use_settings(llm_provider="ollama", ollama_base_url="http://host.docker.internal:11434")
    m = client.get_chat_model("strong")
    assert type(m).__name__ == "ChatOllama" and m.model == "qwen3:4b" and m.temperature == 0
    assert m.reasoning is False and m.base_url == "http://host.docker.internal:11434"
    assert client.structured_method() == "json_schema"
    assert client.timeout_for("fast") == 50.0 and structured.budget_seconds() == 55.0


def test_one_model_name_is_tried_once(use_settings):
    use_settings(llm_provider="ollama")                      # fast = strong, no backup
    assert [c.kind for c in structured._models(None, "fast")] == ["fast"]
    use_settings(llm_provider="ollama", ollama_model_backup="llama3.2:3b")
    assert [c.kind for c in structured._models(None, "fast")] == ["fast", "backup"]


def test_ollama_not_running_gives_the_safe_fallback(use_settings, monkeypatch):
    use_settings(llm_provider="ollama", ollama_base_url="http://127.0.0.1:9")   # nothing listens
    monkeypatch.setattr(structured, "_sleep", lambda s: None, raising=False)
    out = structured.invoke_structured(RouterDecision, [("human", "hi")], kind="fast",
                                       fallback=SAFE)
    assert out == SAFE
