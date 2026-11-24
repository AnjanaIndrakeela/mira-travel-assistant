"""Load the eval cases: the 17 starters from the dataset (unchanged) plus our custom.jsonl."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

EVAL_DIR = Path(__file__).resolve().parent
CUSTOM = EVAL_DIR / "test_cases" / "custom.jsonl"

# The starters have a category but no requirement; this is the brief's mapping.
STARTER_REQUIREMENT = {
    "discovery": "R1", "pricing": "R5", "rates": "R6", "grounding": "R4",
    "safety": "Safety", "off_topic": "Off-topic", "multi_turn": "R5",
}
REQUIREMENT_ORDER = ["R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8", "Booking", "Safety", "Off-topic"]


@dataclass(frozen=True)
class Case:
    id: str
    category: str
    requirement: str
    turns: list[str]
    expected: dict[str, Any]
    retrieval: dict[str, Any] | None = None
    note: str | None = None
    source: str = "custom"                # "starter" or "custom"
    tags: tuple[str, ...] = field(default_factory=tuple)

    @property
    def multi_turn(self) -> bool:
        return len(self.turns) > 1

    @property
    def kind(self) -> str:
        return self.expected["type"]


def load_starters() -> list[Case]:
    from app.data_loader import get_dataset
    return [Case(id=c.id, category=c.category, requirement=STARTER_REQUIREMENT.get(c.category, c.category),
                 turns=list(c.turns), expected=dict(c.expected), source="starter")
            for c in get_dataset().eval_seed]


def load_custom(path: Path = CUSTOM) -> list[Case]:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        c = json.loads(line)
        out.append(Case(id=c["id"], category=c["category"], requirement=c["requirement"], turns=c["turns"],
                        expected=c["expected"], retrieval=c.get("retrieval"), note=c.get("note"),
                        tags=tuple(c.get("tags", ()))))
    return out


def load_cases(*, case_ids: list[str] | None = None, category: str | None = None,
               requirement: str | None = None) -> list[Case]:
    cases = load_starters() + load_custom()
    ids = [c.id for c in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate case IDs")
    if case_ids:
        missing = set(case_ids) - set(ids)
        if missing:
            raise ValueError(f"unknown case(s): {', '.join(sorted(missing))}")
        cases = [c for c in cases if c.id in case_ids]
    if category:
        cases = [c for c in cases if c.category == category]
    if requirement:
        cases = [c for c in cases if c.requirement == requirement]
    return cases
