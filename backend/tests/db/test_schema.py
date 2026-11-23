"""Steps 5.1-5.9: the 8 tables exist, with their rules enforced by Postgres."""

import uuid
from datetime import date

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from app.db.models import ALL_TABLES, ContentItem, Enquiry, Quote, User
from app.db.session import check_database, create_tables


def test_database_is_up(engine):
    assert check_database(engine)


def test_all_eight_tables_exist(engine):
    assert set(ALL_TABLES) <= set(inspect(engine).get_table_names())
    assert len(ALL_TABLES) == 8


def test_create_tables_is_idempotent(engine):
    create_tables(engine)
    create_tables(engine)


def _user(db, role="staff"):
    u = User(email=f"{uuid.uuid4().hex}@test.example", password_hash="x", role=role)
    db.add(u)
    db.flush()
    return u


@pytest.mark.parametrize("make", [
    lambda: User(email="bad@test.example", password_hash="x", role="admin"),
    lambda: Enquiry(kind="complaint"),
    lambda: Enquiry(kind="quote", status="lost"),
    lambda: Quote(status="maybe", tour_id="T01", start_date=date(2027, 1, 10), adults=2),
])
def test_check_constraints(db, make):
    db.add(make())
    with pytest.raises(IntegrityError):
        db.flush()


def test_refusal_row_cannot_carry_a_price(db):
    db.add(Quote(status="needs_specialist", tour_id="T12", start_date=date(2027, 4, 10), adults=1,
                 price_usd=100, cost_usd=50))
    with pytest.raises(IntegrityError):
        db.flush()


def test_ok_row_needs_a_price(db):
    db.add(Quote(status="ok", tour_id="T01", start_date=date(2027, 1, 10), adults=2))
    with pytest.raises(IntegrityError):
        db.flush()


def test_content_cannot_be_published_without_an_approver(db):
    author = _user(db)
    db.add(ContentItem(status="published", title="Ella", body="x", created_by=author.id))
    with pytest.raises(IntegrityError):
        db.flush()


def test_draft_defaults(db):
    author = _user(db)
    item = ContentItem(title="Ella in 3 days", body="Day 1 ...", created_by=author.id)
    db.add(item)
    db.flush()
    assert item.status == "draft" and item.approved_by is None and item.media_ids == []


def test_emails_are_unique(db):
    db.add_all([User(email="same@test.example", password_hash="x", role="staff"),
                User(email="same@test.example", password_hash="y", role="approver")])
    with pytest.raises(IntegrityError):
        db.flush()


def test_psql_lists_the_tables(engine):
    with engine.connect() as conn:
        names = set(conn.scalars(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")))
    assert set(ALL_TABLES) <= names
