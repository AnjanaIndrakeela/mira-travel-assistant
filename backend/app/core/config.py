"""Application settings, loaded from environment variables and the repo-root .env file.

Everything that changes between environments (dates, paths, keys, overrides) lives here,
so the rest of the code never reads os.environ directly.
"""

from datetime import date
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]  # .../Mira/backend
REPO_ROOT = BACKEND_DIR.parent  # .../Mira


def _default_dataset_dir() -> Path:
    """Prefer an untouched copy inside the repo (backend/data/ is what a hosted container
    built from backend/ gets); fall back to the sibling folder."""
    for in_repo in (BACKEND_DIR / "data" / "ceylon-compass-dataset", REPO_ROOT / "data" / "ceylon-compass-dataset"):
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

    # Which LLM writes and reads the chat. "auto" = DeepSeek when DEEPSEEK_API_KEY is set,
    # else Gemini. "ollama" (a local model) is only used when chosen here.
    # Embeddings (search) always use Gemini.
    llm_provider: Literal["auto", "deepseek", "gemini", "ollama"] = "auto"

    # Ollama, a model running on this computer (no key). From Docker the host is
    # host.docker.internal (set in docker-compose.yml). Small models fit a 4 GB GPU.
    ollama_base_url: str = "http://localhost:11434"
    ollama_model_fast: str = "qwen3:4b"
    ollama_model_strong: str = "qwen3:4b"
    ollama_model_backup: str | None = None
    ollama_num_ctx: int = 8192           # room for the prompt, sources and chat history
    ollama_keep_alive: str = "30m"       # keep the model loaded between turns

    # DeepSeek chat (OpenAI-compatible API). SecretStr: logs show '**********', never the key.
    deepseek_api_key: SecretStr | None = None
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model_fast: str = "deepseek-chat"
    deepseek_model_strong: str = "deepseek-chat"
    # A different model to try when the main one fails. Empty = none (same model isn't retried).
    deepseek_model_backup: str | None = None

    # Gemini (embeddings always; chat when the provider is gemini)
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
    # For trace links on the staff page. Empty = looked up once from the Langfuse API.
    langfuse_project_id: str | None = None

    # Staff sessions: how long a sign-in lasts, and whether the cookie needs HTTPS
    # (set MIRA_COOKIE_SECURE=1 when served over HTTPS; localhost is plain HTTP).
    mira_session_hours: float = 8.0
    mira_cookie_secure: bool = False

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

    # Mock payments: 1 = every charge fails (to demo the friendly failure path). The test card
    # 4000 0000 0000 0002 always fails too, whatever this says.
    mock_payment_fail: bool = False

    # CORS origin of the frontend
    frontend_origin: str = "http://localhost:3010"

    @field_validator("mira_margin_day", "mira_margin_multiday", "gemini_api_key",
                     "mira_staff_password", "mira_approver_password",
                     "langfuse_public_key", "langfuse_secret_key", "langfuse_project_id", "gemini_model_backup",
                     "deepseek_api_key", "deepseek_model_backup", "ollama_model_backup",
                     mode="before")
    @classmethod
    def _empty_to_none(cls, v):
        return None if v == "" else v

    @field_validator("database_url", mode="before")
    @classmethod
    def _use_psycopg(cls, v):
        """Hosts such as Render give postgres://... or postgresql://...; SQLAlchemy needs the driver."""
        if isinstance(v, str):
            for prefix in ("postgres://", "postgresql://"):
                if v.startswith(prefix):
                    return "postgresql+psycopg://" + v[len(prefix):]
        return v

    @field_validator("frontend_origin", mode="before")
    @classmethod
    def _no_trailing_slash(cls, v):
        return v.rstrip("/") if isinstance(v, str) else v

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
