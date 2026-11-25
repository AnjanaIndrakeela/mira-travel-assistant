"""Database tests run against the db container, each inside a transaction that is rolled back."""

import pytest
from sqlalchemy.orm import Session

from app.db.session import check_database, create_tables, get_engine


@pytest.fixture(scope="session")
def engine():
    eng = get_engine()
    if not check_database(eng):
        pytest.skip("database not reachable (start it with: docker compose up -d db)")
    create_tables(eng)
    return eng


@pytest.fixture
def db(engine):
    with engine.connect() as conn:
        outer = conn.begin()
        session = Session(bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False)
        try:
            yield session
        finally:
            session.close()
            outer.rollback()
