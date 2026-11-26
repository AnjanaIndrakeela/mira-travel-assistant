"""Export the UI catalog for the frontend (step 11.5), from the Pydantic models (one source of truth).

    python -m app.ui.export [dir]

Writes two files into the frontend's lib folder (mounted in the backend container):
- catalog.schema.json: the catalog's JSON Schema. The frontend's Zod schemas are checked against
  it (`npm run check:catalog`).
- a2ui-catalog.json: the same catalog as an A2UI custom catalog: a catalogId, instructions for the
  agent, and one JSON Schema per component, keyed by its A2UI name (tour_card -> TourCard).
Backend tests fail if either file is out of date.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

from app.ui.catalog import COMPONENT_TYPES, json_schema

DEFAULT_DIR = Path("/frontend/src/lib")
DEFAULT = DEFAULT_DIR / "catalog.schema.json"
A2UI_DEFAULT = DEFAULT_DIR / "a2ui-catalog.json"

CATALOG_ID = "https://ceylon-compass.example/catalog/v1"
A2UI_VERSION = "1.0"
INSTRUCTIONS = (
    "Ceylon Compass Holidays travel components. Use only these components; never invent one. "
    "Prices are never written in a component: price_breakdown and booking_form carry a quote_id "
    "only, and the browser fetches the verified quote. Text props must not contain markup or "
    "money amounts. A trip plan is an unpriced draft our team confirms."
)


def a2ui_name(component_type: str) -> str:
    """tour_card -> TourCard (A2UI component names are PascalCase)."""
    return "".join(part.capitalize() for part in component_type.split("_"))


def render() -> str:
    return json.dumps(json_schema(), indent=2, sort_keys=True) + "\n"


def a2ui_catalog() -> dict:
    """The A2UI custom catalog: each of our components as an A2UI component schema.

    An A2UI component instance is {"id": ..., "component": "TourCard", ...props}, so the
    discriminator `type` becomes the `component` name and an `id` is added. Props, limits and
    `additionalProperties: false` are taken unchanged from the Pydantic models; envelope keys
    starting with "@" (for example @accessibility) are allowed, as the A2UI spec defines them.
    Shared types (Image, SourceRef, PlanDay...) stay in one $defs block."""
    schema = json_schema()
    defs = copy.deepcopy(schema.get("$defs", {}))
    by_type = {d["properties"]["type"]["const"]: name for name, d in defs.items()
               if "const" in d.get("properties", {}).get("type", {})}
    components: dict[str, dict] = {}
    for ctype in COMPONENT_TYPES:
        model = defs.pop(by_type[ctype])
        props = {k: v for k, v in model["properties"].items() if k != "type"}
        required = [r for r in model.get("required", []) if r != "type"]
        name = a2ui_name(ctype)
        components[name] = {
            "type": "object",
            "title": name,
            "description": (model.get("description") or "").strip() or f"The {ctype} component.",
            "x-mira-type": ctype,
            "properties": {"id": {"type": "string", "minLength": 1},
                           "component": {"const": name}, **props},
            "required": ["id", "component", *required],
            "patternProperties": {"^@": {}},
            "additionalProperties": False,
        }
    # the layout root of every reply: its children are the components above, in order
    components["MiraReply"] = {
        "type": "object",
        "title": "MiraReply",
        "description": "One Mira reply: lays out its children (tour cards side by side, a tour's "
                       "days as one list). Always the surface root.",
        "properties": {"id": {"type": "string", "minLength": 1},
                       "component": {"const": "MiraReply"},
                       "children": {"type": "array", "items": {"type": "string", "minLength": 1},
                                    "minItems": 1, "maxItems": 40}},
        "required": ["id", "component", "children"],
        "allowedChildren": sorted(a2ui_name(t) for t in COMPONENT_TYPES),
        "patternProperties": {"^@": {}},
        "additionalProperties": False,
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "catalogId": CATALOG_ID,
        "a2uiVersion": A2UI_VERSION,
        "instructions": INSTRUCTIONS,
        "components": components,
        "functions": {},
        "$defs": defs,
    }


def render_a2ui() -> str:
    return json.dumps(a2ui_catalog(), indent=2, sort_keys=True) + "\n"


def main(argv: list[str]) -> None:
    folder = Path(argv[0]) if argv else DEFAULT_DIR
    for name, text in (("catalog.schema.json", render()), ("a2ui-catalog.json", render_a2ui())):
        path = folder / name
        path.write_text(text, encoding="utf-8")
        print(f"wrote {path}")


if __name__ == "__main__":
    main(sys.argv[1:])
