"""GET /api/v1/health answers and reports the run's key facts."""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:   # "with" runs the lifespan: integrity check + dataset load
        yield c


def test_health_is_ok(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["today"] == "2026-11-19"
    assert body["dataset_found"] is True


def test_health_reports_dataset_loaded_and_unchanged(client):
    body = client.get("/api/v1/health").json()
    assert body["dataset_integrity"] == "ok"
    assert body["data_issues"] == 30


def test_health_reports_every_check(client):
    body = client.get("/api/v1/health").json()
    assert set(body) == {"status", "today", "dataset_found", "dataset_integrity", "data_issues",
                         "database", "tracing", "llm_configured", "llm_provider", "index"}
    assert body["llm_provider"] in {"deepseek", "gemini"}
    assert body["database"] in {"ok", "unavailable"}


def test_health_never_shows_the_api_key(client):
    text = client.get("/api/v1/health").text
    assert "gemini_api_key" not in text and "deepseek_api_key" not in text and "sk-" not in text


def test_old_unversioned_path_is_404(client):
    assert client.get("/health").status_code == 404
