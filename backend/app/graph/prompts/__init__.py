"""Prompts are Markdown files in this folder, loaded by name and versioned in git.

Placeholders use {name}; a missing value raises KeyError, so nothing is sent half-rendered.
PROMPT_VERSION goes into every trace so eval results can be tied to the prompt text.
"""

from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path

PROMPTS_DIR = Path(__file__).parent
PROMPT_VERSION = "2026-11-23.1"


@lru_cache
def _raw(name: str) -> str:
    return (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")


def load_prompt(name: str, **values) -> str:
    return _raw(name).format(**values)


def system_prompt(today: date, brand=None) -> str:
    """The system prompt with the brand voice injected from the brand pack (never copied by hand)."""
    if brand is None:
        from app.data_loader import get_dataset
        brand = get_dataset().brand
    voice = "\n".join(f"- {line}" for line in brand.tone_of_voice)
    return load_prompt("system", assistant_name=brand.assistant_name, company=brand.name,
                       today=today.strftime("%A %d %B %Y"), tone_of_voice=voice)
