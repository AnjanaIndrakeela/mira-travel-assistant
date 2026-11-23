"""Every UI payload is checked against the catalog before it reaches the browser (step 11.4).

- unknown type             -> dropped, logged, reported for the trace
- bad or extra props       -> dropped (includes markup/script and money amounts in text)
- price_breakdown / booking_form whose quote_id isn't this turn's saved, priced quote
                           -> dropped (a price component can only point at a verified quote)
Valid components come back as plain JSON dicts in the catalog's own shape.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import ValidationError

from app.ui.catalog import ADAPTER, COMPONENT_TYPES

logger = logging.getLogger("mira.ui")
NEEDS_QUOTE = {"price_breakdown", "booking_form"}


def validate_ui(components: list[Any], *, quote_id: str | None) -> tuple[list[dict], list[dict]]:
    """Return (valid components, rejections). A rejection is {type, reason} with no prop values,
    so nothing personal or forged is copied into logs or traces."""
    valid: list[dict] = []
    rejected: list[dict] = []
    for raw in components:
        kind = raw.get("type") if isinstance(raw, dict) else None
        name = kind if isinstance(kind, str) and kind in COMPONENT_TYPES else "unknown"
        if name == "unknown":
            rejected.append({"type": "unknown", "reason": "unknown_type"})
            continue
        try:
            component = ADAPTER.validate_python(raw)
        except ValidationError as exc:
            fields = sorted({".".join(str(p) for p in e["loc"][1:2]) or e["type"] for e in exc.errors()})
            rejected.append({"type": name, "reason": "invalid_props", "fields": fields})
            continue
        if name in NEEDS_QUOTE and str(component.quote_id) != str(quote_id or ""):
            rejected.append({"type": name, "reason": "no_saved_quote"})
            continue
        valid.append(component.model_dump(mode="json"))
    for r in rejected:
        logger.warning("UI component dropped: %s (%s)", r["type"], r["reason"])
    return valid, rejected
