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
    engine = engine or get_engine()
    Base.metadata.create_all(engine)
    upgrade_schema(engine)


def upgrade_schema(engine: Engine) -> None:
    """Small in-place changes create_all can't make (idempotent, safe on every start).

    Phase 13: enquiry statuses became new / contacted / pending / confirmed / closed.
    Rows saved as 'in_progress' before that become 'contacted'."""
    from typing import get_args

    from app.db.models import EnquiryStatus
    allowed = ", ".join(f"'{v}'" for v in get_args(EnquiryStatus))
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE enquiries DROP CONSTRAINT IF EXISTS ck_enquiries_status_allowed"))
        conn.execute(text("UPDATE enquiries SET status = 'contacted' WHERE status = 'in_progress'"))
        conn.execute(text(f"ALTER TABLE enquiries ADD CONSTRAINT ck_enquiries_status_allowed "
                          f"CHECK (status IN ({allowed}))"))
        # photos with credits (open-licence tour pictures)
        conn.execute(text("ALTER TABLE media ADD COLUMN IF NOT EXISTS kind VARCHAR(20) NOT NULL DEFAULT 'illustration'"))
        for col, size in (("credit", 200), ("licence", 40), ("licence_url", 300), ("source", 300)):
            conn.execute(text(f"ALTER TABLE media ADD COLUMN IF NOT EXISTS {col} VARCHAR({size})"))
        # full mock card form: keep the card type and last four digits only
        conn.execute(text("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS card_brand VARCHAR(20)"))
        conn.execute(text("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS card_last4 VARCHAR(4)"))
