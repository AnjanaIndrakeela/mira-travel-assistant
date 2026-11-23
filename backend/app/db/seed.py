"""Seed demo data. Idempotent: running it again changes nothing.

- Two staff accounts (staff, approver). Passwords come only from .env (MIRA_STAFF_PASSWORD,
  MIRA_APPROVER_PASSWORD) and are stored hashed. No password set = account not created.
- Our own Ella media (backend/media/<tag>/media.json) registered in the `media` table.

    python -m app.db.seed
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.security import hash_password
from app.db.models import Media, User

logger = logging.getLogger("mira.seed")


@dataclass
class SeedReport:
    users_created: list[str] = field(default_factory=list)
    users_skipped: list[str] = field(default_factory=list)     # no password in .env
    media_created: int = 0

    def summary(self) -> str:
        return (f"users created: {self.users_created or 'none'}; skipped (no password set): "
                f"{self.users_skipped or 'none'}; media rows created: {self.media_created}")


def seed_users(session: Session, settings: Settings, report: SeedReport) -> None:
    accounts = [(settings.mira_staff_email, settings.mira_staff_password, "staff"),
                (settings.mira_approver_email, settings.mira_approver_password, "approver")]
    for email, password, role in accounts:
        email = email.strip().lower()
        if session.scalar(select(User).where(User.email == email)):
            continue                                   # already there: never overwrite
        if password is None:
            report.users_skipped.append(role)
            continue
        session.add(User(email=email, role=role, password_hash=hash_password(password.get_secret_value())))
        report.users_created.append(role)


def seed_media(session: Session, media_dir: Path, report: SeedReport) -> None:
    existing = set(session.scalars(select(Media.path)))
    for manifest in sorted(media_dir.glob("*/media.json")):
        for entry in json.loads(manifest.read_text(encoding="utf-8")):
            path = f"{manifest.parent.name}/{entry['file']}"
            if path in existing:
                continue
            if not (manifest.parent / entry["file"]).is_file():
                raise FileNotFoundError(f"{manifest} lists missing file {entry['file']}")
            session.add(Media(tag=entry["tag"], path=path, alt=entry["alt"]))
            report.media_created += 1


def seed(session: Session, settings: Settings | None = None) -> SeedReport:
    settings = settings or get_settings()
    report = SeedReport()
    seed_users(session, settings, report)
    seed_media(session, settings.mira_media_dir, report)
    session.flush()
    return report


def main() -> None:
    from app.db.session import create_tables, get_sessionmaker
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    create_tables()
    with get_sessionmaker()() as session, session.begin():
        report = seed(session)
    logger.info(report.summary())


if __name__ == "__main__":
    main()
