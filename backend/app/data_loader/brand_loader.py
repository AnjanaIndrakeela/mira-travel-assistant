"""Load the brand pack (colours, type, spacing, tone of voice) used by the UI and prompts."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict

BRAND_RELATIVE_PATH = Path("brand") / "brand_pack.json"


class BrandColors(BaseModel):
    model_config = ConfigDict(extra="allow")
    black: str
    white: str
    orange: str
    accents: dict[str, str]
    surface: str
    text: str
    muted_text: str
    border: str


class BrandPack(BaseModel):
    model_config = ConfigDict(extra="allow")
    name: str
    assistant_name: str
    colors: BrandColors
    typography: dict
    spacing_px: list[int]
    radius_px: dict[str, int]
    cards: dict
    motion: dict
    tone_of_voice: list[str]
    do_not: list[str]


def load_brand(dataset_dir: Path) -> BrandPack:
    raw = json.loads((dataset_dir / BRAND_RELATIVE_PATH).read_text(encoding="utf-8"))
    return BrandPack.model_validate(raw)
