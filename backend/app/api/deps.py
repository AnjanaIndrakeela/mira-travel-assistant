"""FastAPI dependencies: a database session per request, and the chat graph.
Tests override both (a rolled-back session, a graph with fake models)."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy.orm import Session

from app.db.session import get_sessionmaker


def get_db() -> Iterator[Session]:
    """One session per request. Routes commit what must be kept; the rest is rolled back."""
    with get_sessionmaker()() as session:
        yield session


def get_chat_graph():
    from app.graph.build import get_graph
    return get_graph()
