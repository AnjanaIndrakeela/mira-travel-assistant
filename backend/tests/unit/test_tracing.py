"""Trace shape rules (Langfuse best practices): node types, noise filter, names, environment."""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.graph import tracing
from app.graph.tracing import NODE_TYPES, is_noise, make_langfuse, observe


@pytest.mark.parametrize("name", ["RunnableWithFallbacks", "RunnableLambda", "PydanticOutputParser",
                                  "RunnableAssign<parsed,parsing_error>",
                                  "RunnableParallel<parsed,parsing_error>", "_after_guard"])
def test_langchain_plumbing_is_not_exported(name):
    assert is_noise(name)


@pytest.mark.parametrize("name", ["mira-turn", "chat-graph", "guard", "retrieve", "analyse-turn",
                                  "analyse-turn-generation", "RunnableParallel<raw>", None])
def test_steps_and_parents_of_generations_are_kept(name):
    # RunnableParallel<raw> holds the generation: dropping it would orphan the model call
    assert not is_noise(name)


def test_graph_nodes_get_their_real_observation_type():
    handler = tracing._handler_class()()
    kind = handler._get_observation_type_from_serialized
    assert kind({}, "chain", name="guard") == "guardrail"
    assert kind({}, "chain", name="retrieve") == "retriever"
    assert kind({}, "chain", name="price") == "tool"
    assert kind({}, "chain", name="plan_trip") == "agent"
    assert kind({}, "chain", name="discovery") == "chain"
    assert kind({}, "llm", name="analyse-turn-generation") == "generation"
    assert set(NODE_TYPES.values()) <= {"guardrail", "retriever", "tool", "agent"}


def test_the_client_reports_environment_and_release(monkeypatch):
    seen = {}

    class FakeLangfuse:
        def __init__(self, **kw):
            seen.update(kw)

    import langfuse
    monkeypatch.setattr(langfuse, "Langfuse", FakeLangfuse)
    s = Settings(langfuse_public_key="pk-test", langfuse_secret_key="sk-test",
                 langfuse_tracing_environment="staging", langfuse_release="abc123")
    assert isinstance(make_langfuse(s), FakeLangfuse)
    assert seen["environment"] == "staging" and seen["release"] == "abc123"
    assert seen["should_export_span"] is tracing.export_span and seen["mask"] is tracing.mask_trace


def test_observe_without_langfuse_runs_untraced(monkeypatch):
    monkeypatch.setattr(tracing, "get_langfuse", lambda: None)
    with observe("write-tour-draft", input="x", tags=["content-writer"]) as t:
        pass
    assert t.callbacks == [] and t.trace_id is None
    t.finish(output="ignored")          # no root: a no-op, never an error


def test_structured_calls_are_named_in_traces():
    from langchain_core.messages import HumanMessage
    from pydantic import BaseModel

    from app.llm.structured import invoke_structured

    class Out(BaseModel):
        ok: bool

    seen = {}

    class Fake:
        def with_structured_output(self, schema, **_):
            return self

        def invoke(self, messages, config=None):
            seen.update(config or {})
            return {"parsed": Out(ok=True)}

    assert invoke_structured(Out, [HumanMessage(content="hi")], model=Fake(), name="analyse-turn").ok
    assert seen["run_name"] == "analyse-turn"


def test_a_failed_run_marks_its_root_as_error():
    seen = []

    class Span:
        def update(self, **kw):
            seen.append(kw)

    tracing.Traced(span=Span()).finish(output={"errors": ["bad"]}, error="bad")
    tracing.Traced(span=Span()).finish(output="ok")
    assert seen[0]["level"] == "ERROR" and seen[0]["status_message"] == "bad"
    assert "level" not in seen[1]
