"""Mira's evaluation suite: cases, code assertions, an in-process runner and the report.

Run inside the backend container (the repo's evaluation/ folder is mounted at /evaluation):

    docker compose exec -w / backend python -m evaluation.runner [--case S02] [--category pricing]
"""

import sys
from pathlib import Path

# The backend package: ../backend in the repo, /app in the container.
for _root in (Path(__file__).resolve().parents[1] / "backend", Path("/app")):
    if (_root / "app" / "main.py").is_file():
        if str(_root) not in sys.path:
            sys.path.insert(0, str(_root))
        break
