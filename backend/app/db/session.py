"""Database engine and session factory."""

from functools import lru_cache

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


@lru_cache
def get_engine() -> Engine:
    return create_engine(get_settings().database_url, pool_pre_ping=True)


def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def check_database(engine: Engine | None = None) -> bool:
    """Return True if a trivial query succeeds. Never raises: health must always answer."""
    try:
        with (engine or get_engine()).connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def create_tables(engine: Engine | None = None) -> None:
    """Create any missing tables (idempotent). Existing tables and data are left alone."""
    from app.db import models  # noqa: F401  (registers the tables on Base.metadata)
    from app.db.base import Base
    Base.metadata.create_all(engine or get_engine())
