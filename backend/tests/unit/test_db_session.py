"""check_database(): True when Postgres answers, False (never an exception) when it doesn't."""

from urllib.parse import urlparse

import pytest
from sqlalchemy import create_engine

from app.core.config import get_settings
from app.db.session import check_database

IN_COMPOSE = urlparse(get_settings().database_url).hostname == "db"


def test_unreachable_database_returns_false():
    # Port 1 on localhost: nothing listens there, so the connection is refused quickly.
    engine = create_engine("postgresql+psycopg://x:x@127.0.0.1:1/x",
                           connect_args={"connect_timeout": 2})
    assert check_database(engine) is False


@pytest.mark.skipif(not IN_COMPOSE, reason="needs the compose 'db' service")
def test_compose_database_answers():
    assert check_database() is True
