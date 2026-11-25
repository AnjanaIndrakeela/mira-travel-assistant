"""Export the UI catalog's JSON Schema for the frontend (step 11.5).

    python -m app.ui.export [path]

Default path: /frontend/src/lib/catalog.schema.json (the frontend's lib folder, mounted in the
backend container). The frontend's Zod schemas are checked against this file
(`npm run check:catalog`), and a backend test fails if the file is out of date.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from app.ui.catalog import json_schema

DEFAULT = Path("/frontend/src/lib/catalog.schema.json")


def render() -> str:
    return json.dumps(json_schema(), indent=2, sort_keys=True) + "\n"


def main(argv: list[str]) -> None:
    path = Path(argv[0]) if argv else DEFAULT
    path.write_text(render(), encoding="utf-8")
    print(f"wrote {path}")


if __name__ == "__main__":
    main(sys.argv[1:])
