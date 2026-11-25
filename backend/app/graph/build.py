"""Wires the nodes into a LangGraph StateGraph (step 8.13).

    load_visitor (1st turn: R2 known slots) -> guard -> (discovery) -> route -> ask/greet/decline ............ -> respond
                                  -> price -> (retrieve) .......... -> respond
                                  -> match_tours .................. -> respond
                                  -> retrieve ..................... -> respond
    respond -> persist (quote, enquiry, trace_id) -> build_ui (output guard) -> END

The checkpointer keeps each conversation's state between turns, keyed by thread_id. The app
keeps it in Postgres, so a restart doesn't make Mira forget a chat; tests use memory.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from app.graph.nodes import NO_TOOLS, Deps, Nodes
from app.graph.state import MiraState


def _after_guard(state: MiraState) -> str:
    return "route" if state["intent"] in NO_TOOLS else "discovery"


def _after_route(state: MiraState) -> str:
    return {"price": "price", "match_tours": "match_tours", "retrieve": "retrieve"}.get(
        state["action"], "respond")


def _after_price(state: MiraState) -> str:
    return "retrieve" if state.get("needs_retrieval") and state["intent"] == "tour_info" else "respond"


def build_graph(deps: Deps | None = None, checkpointer=None):
    n = Nodes(deps or Deps.default())
    g = StateGraph(MiraState)
    for name in ("load_visitor", "guard", "discovery", "route", "retrieve", "price", "match_tours",
                 "respond", "build_ui", "persist"):
        g.add_node(name, getattr(n, name))
    g.add_edge(START, "load_visitor")
    g.add_edge("load_visitor", "guard")
    g.add_conditional_edges("guard", _after_guard, ["discovery", "route"])
    g.add_edge("discovery", "route")
    g.add_conditional_edges("route", _after_route, ["price", "match_tours", "retrieve", "respond"])
    g.add_conditional_edges("price", _after_price, ["retrieve", "respond"])
    g.add_edge("match_tours", "respond")
    g.add_edge("retrieve", "respond")
    g.add_edge("respond", "persist")
    g.add_edge("persist", "build_ui")
    g.add_edge("build_ui", END)
    return g.compile(checkpointer=checkpointer if checkpointer is not None else InMemorySaver())


logger = logging.getLogger("mira.graph")


def postgres_checkpointer():
    """Chat memory in Postgres (tables made on first use). If the database can't be reached,
    memory only: the chat still works, it just forgets on restart."""
    from app.core.config import get_settings
    try:
        from langgraph.checkpoint.postgres import PostgresSaver
        from psycopg.rows import dict_row
        from psycopg_pool import ConnectionPool
        url = get_settings().database_url.replace("postgresql+psycopg://", "postgresql://")
        pool = ConnectionPool(url, min_size=1, max_size=8, open=True, timeout=10,
                              kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row})
        saver = PostgresSaver(pool)
        saver.setup()
        return saver
    except Exception as exc:  # noqa: BLE001
        logger.warning("chat memory is in-memory only (%s)", exc.__class__.__name__)
        return InMemorySaver()


@lru_cache
def get_graph():
    """The app's graph: real models, the dataset, and chat memory in Postgres."""
    return build_graph(checkpointer=postgres_checkpointer())


def mermaid() -> str:
    return build_graph(Deps.default()).get_graph().draw_mermaid()


if __name__ == "__main__":
    print(mermaid())
