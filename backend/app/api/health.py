"""Health endpoint: liveness plus the facts that matter for a correct run."""

from fastapi import APIRouter

from app.core.config import get_settings
from app.db.session import check_database

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "today": settings.mira_today.isoformat(),
        "dataset_found": settings.mira_dataset_dir.is_dir(),
        "database": "ok" if check_database() else "unavailable",
        "tracing": "enabled" if settings.tracing_enabled else "disabled",
        "llm_configured": settings.gemini_api_key is not None,
    }
