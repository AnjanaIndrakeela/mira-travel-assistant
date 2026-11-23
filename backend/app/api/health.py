"""Health endpoint: liveness plus the facts that matter for a correct run."""

from fastapi import APIRouter, Request

from app.core.config import get_settings
from app.db.session import check_database

router = APIRouter(tags=["health"])


@router.get("/health")
def health(request: Request) -> dict:
    settings = get_settings()
    dataset = getattr(request.app.state, "dataset", None)
    integrity_ok = getattr(request.app.state, "dataset_integrity_ok", None)
    return {
        "status": "ok",
        "today": settings.mira_today.isoformat(),
        "dataset_found": settings.mira_dataset_dir.is_dir(),
        "dataset_integrity": "not_checked" if integrity_ok is None else ("ok" if integrity_ok else "failed"),
        "data_issues": len(dataset.issues) if dataset else None,
        "database": "ok" if check_database() else "unavailable",
        "tracing": "enabled" if settings.tracing_enabled else "disabled",
        "llm_configured": settings.gemini_api_key is not None,
    }
