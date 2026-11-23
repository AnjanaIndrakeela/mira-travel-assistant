"""Application settings, loaded from environment variables and the repo-root .env file.

Everything that changes between environments (dates, paths, keys, overrides) lives here,
so the rest of the code never reads os.environ directly.
"""

from datetime import date
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]  # .../Mira/backend
REPO_ROOT = BACKEND_DIR.parent  # .../Mira


def _default_dataset_dir() -> Path:
    """Prefer an untouched copy inside the repo; fall back to the sibling folder."""
    in_repo = REPO_ROOT / "data" / "ceylon-compass-dataset"
    if in_repo.is_dir():
        return in_repo
    return REPO_ROOT.parent / "ceylon-compass-dataset"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # "Today" is configurable: the starter evals assume 19 November 2026.
    mira_today: date = date(2026, 11, 19)

    # The supplied dataset. Read-only: the app never writes to this folder.
    mira_dataset_dir: Path = Field(default_factory=_default_dataset_dir)

    # PostgreSQL (docker-compose service "db" is on host port 5433).
    database_url: str = "postgresql+psycopg://mira:mira@localhost:5433/mira"

    # Gemini
    # SecretStr: printing or logging Settings shows '**********', never the key.
    gemini_api_key: SecretStr | None = None
    # Gemini 2.5 models return 404 for new API keys, so the defaults are Gemini 3.
    gemini_model_fast: str = "gemini-3.1-flash-lite"
    gemini_model_strong: str = "gemini-3.5-flash"
    # Tried last when both models above are overloaded (503) or out of quota (429): quotas
    # are per model, so a third model keeps chat working. Empty = no backup.
    gemini_model_backup: str | None = "gemini-3.5-flash-lite"
    # gemini-embedding-2: compared with gemini-embedding-001 on our content, both found the
    # right page for all test questions, but -2 separates relevant from irrelevant more clearly.
    gemini_embedding_model: str = "gemini-embedding-2"
    gemini_embedding_dims: int = 768  # enough for ~150 chunks; 1536 or 3072 also supported

    # Langfuse tracing (optional: the app runs without it)
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str = "https://cloud.langfuse.com"

    # Pricing overrides. Empty = use the values from the workbook's Settings tab.
    # Used for the live "change a margin rule" demo without editing the workbook.
    mira_margin_day: Decimal | None = None
    mira_margin_multiday: Decimal | None = None

    # Demo staff accounts, created by app.db.seed. Passwords only from .env, stored hashed.
    # No password set = that account is not created (never a default password).
    mira_staff_email: str = "staff@ceylon-compass.example"
    mira_staff_password: SecretStr | None = None
    mira_approver_email: str = "approver@ceylon-compass.example"
    mira_approver_password: SecretStr | None = None

    # Our own media library (R8 "Ella photos"; the dataset has none)
    mira_media_dir: Path = BACKEND_DIR / "media"

    # CORS origin of the frontend
    frontend_origin: str = "http://localhost:3000"

    @field_validator("mira_margin_day", "mira_margin_multiday", "gemini_api_key",
                     "mira_staff_password", "mira_approver_password",
                     "langfuse_public_key", "langfuse_secret_key", "gemini_model_backup", mode="before")
    @classmethod
    def _empty_to_none(cls, v):
        return None if v == "" else v

    @field_validator("mira_dataset_dir", mode="before")
    @classmethod
    def _empty_dataset_dir_to_default(cls, v):
        return _default_dataset_dir() if v in ("", None) else v

    @property
    def tracing_enabled(self) -> bool:
        return bool(self.langfuse_public_key and self.langfuse_secret_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
