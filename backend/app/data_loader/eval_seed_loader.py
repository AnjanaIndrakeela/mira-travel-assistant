"""Load the supplied starter evaluation cases (evals/eval_seed.jsonl) exactly as given."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

EVAL_SEED_PATH = Path("evals") / "eval_seed.jsonl"


class EvalCase(BaseModel):
    id: str
    category: str
    turns: list[str]
    expected: dict        # type: quote | quote_sequence | flag_no_price | behaviour, plus details


def load_eval_seed(dataset_dir: Path) -> list[EvalCase]:
    lines = (dataset_dir / EVAL_SEED_PATH).read_text(encoding="utf-8").splitlines()
    return [EvalCase.model_validate(json.loads(line)) for line in lines if line.strip()]
