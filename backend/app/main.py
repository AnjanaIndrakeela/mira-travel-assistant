"""FastAPI entry point for Mira."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.db.session import check_database

settings = get_settings()

app = FastAPI(title="Mira – Ceylon Compass Holidays", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/v1/health")
def health() -> dict:
    """Liveness plus the facts that matter for a correct run."""
    return {
        "status": "ok",
        "today": settings.mira_today.isoformat(),
        "dataset_found": settings.mira_dataset_dir.is_dir(),
        "database": "ok" if check_database() else "unavailable",
        "tracing": "enabled" if settings.tracing_enabled else "disabled",
        "llm_configured": settings.gemini_api_key is not None,
    }
