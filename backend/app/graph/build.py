"""Wires the nodes into a LangGraph StateGraph (step 8.13).

    guard -> (discovery) -> route -> ask/greet/decline ............ -> respond
                                  -> price -> (retrieve) .......... -> respond
                                  -> match_tours .................. -> respond
                                  -> retrieve ..................... -> respond
    respond -> build_ui (output guard) -> persist -> END

The checkpointer keeps each conversation's state between turns, keyed by thread_id.
"""

from __future__ import annotations

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
    for name in ("guard", "discovery", "route", "retrieve", "price", "match_tours",
                 "respond", "build_ui", "persist"):
        g.add_node(name, getattr(n, name))
    g.add_edge(START, "guard")
    g.add_conditional_edges("guard", _after_guard, ["discovery", "route"])
    g.add_edge("discovery", "route")
    g.add_conditional_edges("route", _after_route, ["price", "match_tours", "retrieve", "respond"])
    g.add_conditional_edges("price", _after_price, ["retrieve", "respond"])
    g.add_edge("match_tours", "respond")
    g.add_edge("retrieve", "respond")
    g.add_edge("respond", "build_ui")
    g.add_edge("build_ui", "persist")
    g.add_edge("persist", END)
    return g.compile(checkpointer=checkpointer if checkpointer is not None else InMemorySaver())


@lru_cache
def get_graph():
    """The app's graph: real models, the dataset, and an in-memory checkpointer."""
    return build_graph()


def mermaid() -> str:
    return build_graph(Deps.default()).get_graph().draw_mermaid()


if __name__ == "__main__":
    print(mermaid())
