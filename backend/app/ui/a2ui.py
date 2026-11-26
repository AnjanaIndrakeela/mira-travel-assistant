"""Mira's validated UI components as A2UI v1.0 messages (step 4 of the A2UI move).

build_ui picks components and app.guards.ui_validator checks them against the Pydantic catalog
FIRST. Only components that passed are converted here, so the brief's "validate every UI payload
before it reaches the browser" still holds; to_a2ui() then checks each converted component
again by converting it back and re-validating it (a round trip), and drops any that fail.

One reply = one surface:
  {"version": "1.0", "createSurface": {"surfaceId", "catalogId"}}
  {"version": "1.0", "updateComponents": {"surfaceId", "components": [root, ...]}}
The root is our catalog's MiraReply layout component; its children are our components in the
order build_ui chose (the browser keeps tour cards side by side and a tour's days in one list).
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import ValidationError

from app.ui.catalog import ADAPTER
from app.ui.export import A2UI_VERSION, CATALOG_ID, a2ui_name

logger = logging.getLogger("mira.ui.a2ui")
ROOT_ID = "root"
ROOT_COMPONENT = "MiraReply"
NAME_TO_TYPE: dict[str, str] = {}      # TourCard -> tour_card, filled on first use


def to_component(c: dict, component_id: str) -> dict:
    """{"type": "tour_card", ...} -> {"id": ..., "component": "TourCard", ...}."""
    props = {k: v for k, v in c.items() if k != "type"}
    return {"id": component_id, "component": a2ui_name(c["type"]), **props}


def from_component(a: dict) -> dict:
    """The reverse of to_component (for the round-trip check and for clients that need it)."""
    if not NAME_TO_TYPE:
        from app.ui.catalog import COMPONENT_TYPES
        NAME_TO_TYPE.update({a2ui_name(t): t for t in COMPONENT_TYPES})
    props = {k: v for k, v in a.items() if k not in {"id", "component"} and not k.startswith("@")}
    return {"type": NAME_TO_TYPE[a["component"]], **props}


def _round_trip_ok(a: dict, original: dict) -> bool:
    """True when the card is valid today and converts back to exactly the same card. Saved chats
    can hold cards from an older catalog, so an invalid original is a False, not an error."""
    try:
        want = ADAPTER.validate_python(original).model_dump(mode="json", exclude_none=False)
        back = ADAPTER.validate_python(from_component(a)).model_dump(mode="json", exclude_none=False)
    except (KeyError, ValidationError):
        return False
    return back == want


def to_a2ui(ui: list[dict[str, Any]], surface_id: str) -> list[dict[str, Any]]:
    """The A2UI messages for one reply's validated components ([] when there are none)."""
    components = []
    for i, c in enumerate(ui, start=1):
        if not isinstance(c, dict) or not isinstance(c.get("type"), str):
            logger.warning("A2UI conversion dropped a card with no type")
            continue
        a = to_component(c, f"c{i}")
        if _round_trip_ok(a, c):
            components.append(a)
        else:          # a live reply was validated first, so this is a card an older app version saved
            logger.warning("A2UI conversion dropped a %s component", c.get("type"))
    if not components:
        return []
    root = {"id": ROOT_ID, "component": ROOT_COMPONENT, "children": [a["id"] for a in components]}
    return [
        {"version": A2UI_VERSION, "createSurface": {"surfaceId": surface_id, "catalogId": CATALOG_ID}},
        {"version": A2UI_VERSION, "updateComponents": {"surfaceId": surface_id,
                                                       "components": [root, *components]}},
    ]
