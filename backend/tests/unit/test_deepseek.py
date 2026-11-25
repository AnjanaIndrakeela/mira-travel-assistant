"""DeepSeek as the chat provider: chosen by key, function-calling structured output, no
second try on the same model name, and its errors handled like Gemini's. Offline: no API call."""

import pytest

from app.core.config import Settings
from app.llm import client, structured
from app.llm.schemas import Intent, RouterDecision

pytestmark = pytest.mark.deepseek
GOOD = RouterDecision(intent=Intent.QUOTE, needs_retrieval=False)
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


def test_provider_follows_the_keys(use_settings):
    use_settings(deepseek_api_key="test-key", gemini_api_key="g")
    assert client.provider() == "deepseek" and client.llm_configured()
    use_settings(gemini_api_key="g")
    assert client.provider() == "gemini"
    use_settings(deepseek_api_key="test-key", llm_provider="gemini", gemini_api_key="g")
    assert client.provider() == "gemini"
    use_settings(llm_provider="deepseek")
    assert client.provider() == "deepseek" and not client.llm_configured()


def test_deepseek_model_is_built_without_showing_the_key(use_settings):
    use_settings(deepseek_api_key="test-secret-123")
    m = client.get_chat_model("fast")
    assert type(m).__name__ == "ChatDeepSeek" and m.model_name == "deepseek-chat" and m.temperature == 0
    assert "test-secret-123" not in repr(m)
    assert client.structured_method() == "function_calling" and client.timeout_for("strong") == 30.0


def test_missing_deepseek_key_is_reported(use_settings):
    use_settings(llm_provider="deepseek")
    with pytest.raises(client.LLMNotConfigured, match="DEEPSEEK_API_KEY"):
        client.get_chat_model("fast")


def test_same_model_is_not_tried_twice(use_settings):
    use_settings(deepseek_api_key="k")                       # fast = strong = deepseek-chat, no backup
    assert [c.kind for c in structured._models(None, "fast")] == ["fast"]
    use_settings(deepseek_api_key="k", deepseek_model_backup="deepseek-reasoner")
    assert [c.kind for c in structured._models(None, "strong")] == ["strong", "backup"]


class Fake:
    def __init__(self, *outputs):
        self.outputs, self.methods = list(outputs), []

    def with_structured_output(self, schema, method=None, include_raw=False):
        self.methods.append(method)
        fake = self

        class Bound:
            def invoke(self, messages, config=None):
                out = fake.outputs.pop(0)
                if isinstance(out, Exception):
                    raise out
                return {"raw": None, "parsed": out, "parsing_error": None}
        return Bound()


def test_structured_calls_use_function_calling(use_settings, monkeypatch):
    use_settings(deepseek_api_key="k")
    monkeypatch.setattr(structured, "_resting_until", {})
    fake = Fake(GOOD)
    monkeypatch.setattr(structured, "get_chat_model", lambda kind="fast": fake)
    assert invoke_ok(fake)


def invoke_ok(fake):
    out = structured.invoke_structured(RouterDecision, [], fallback=SAFE)
    return out.intent is Intent.QUOTE and fake.methods == ["function_calling"]


def _err(name, text=""):
    return type(name, (Exception,), {})(text)


@pytest.mark.parametrize("exc, kind", [
    (_err("APITimeoutError", "Request timed out."), "timeout"),
    (_err("RateLimitError", "Error code: 429"), "quota"),
    (_err("APIConnectionError", "Connection error."), "overloaded"),
    (_err("InternalServerError", "Error code: 503 - Server overloaded"), "overloaded"),
    (_err("AuthenticationError", "Error code: 401 - invalid api key"), "other"),
])
def test_deepseek_errors_are_classified(exc, kind):
    assert structured.error_kind(exc) == kind


def test_deepseek_failure_gives_the_safe_fallback(use_settings, monkeypatch):
    use_settings(deepseek_api_key="k")
    monkeypatch.setattr(structured, "_resting_until", {})
    monkeypatch.setattr(structured, "_sleep", lambda s: None)
    fake = Fake(_err("APITimeoutError", "timed out"))
    monkeypatch.setattr(structured, "get_chat_model", lambda kind="fast": fake)
    assert structured.invoke_structured(RouterDecision, [], fallback=SAFE) is SAFE


def test_deepseek_timeouts_fit_the_budget():
    t = client.DEEPSEEK_TIMEOUT_S
    assert t["fast"] + t["backup"] <= structured.DEEPSEEK_BUDGET_SECONDS
    assert t["strong"] + t["backup"] <= structured.DEEPSEEK_BUDGET_SECONDS
