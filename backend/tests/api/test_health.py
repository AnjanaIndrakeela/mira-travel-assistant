"""GET /api/v1/health answers and reports the run's key facts."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_is_ok():
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["today"] == "2026-11-19"
    assert body["dataset_found"] is True


def test_health_reports_every_check():
    body = client.get("/api/v1/health").json()
    assert set(body) == {"status", "today", "dataset_found", "database", "tracing",
                         "llm_configured"}
    assert body["database"] in {"ok", "unavailable"}  # "ok" once compose runs the db (1.14)


def test_health_never_shows_the_api_key():
    assert "gemini_api_key" not in client.get("/api/v1/health").text


def test_old_unversioned_path_is_404():
    assert client.get("/health").status_code == 404
