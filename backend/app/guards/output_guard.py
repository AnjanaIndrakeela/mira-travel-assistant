"""Checks on every reply before the traveller sees it (plan §16 step 9).

- Any money amount that is not in this turn's verified quote: its sentence is replaced with
  "A travel specialist will confirm the exact price." (an invented price can't get through)
- Any sentence naming internal figures or terms (cost, margin, profit, LKR rates, the rate
  workbook) is removed.
Runs on every reply, including handoffs and small talk. No LLM calls; deterministic.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from pydantic import BaseModel

PRICE_LINE = "A travel specialist will confirm the exact price."

AMOUNT = re.compile(
    r"(?:US\$|USD|\$|LKR|Rs\.?|SLR|€|£|EUR|GBP)\s?(?P<a>\d[\d,]*(?:\.\d+)?)\s?(?P<k>k\b)?"
    r"|(?P<b>\d[\d,]*(?:\.\d+)?)\s?(?P<k2>k\b)?\s?(?:USD|US dollars|dollars|LKR|rupees|euros?|pounds)\b",
    re.IGNORECASE,
)
INTERNAL = re.compile(
    r"\b(margin|mark-?up|gross profit|profit|gp ?%|cost price|our costs?|internal costs?|net rates?|"
    r"supplier rates?|buy rates?|rate sheet|rate workbook|workbook|LKR)\b",
    re.IGNORECASE,
)
SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


class OutputCheck(BaseModel):
    text: str
    price_stripped: int = 0
    internal_stripped: int = 0

    @property
    def changed(self) -> bool:
        return bool(self.price_stripped or self.internal_stripped)


def amounts_in(text: str) -> list[int]:
    out = []
    for m in AMOUNT.finditer(text):
        raw = (m.group("a") or m.group("b")).replace(",", "")
        value = float(raw) * (1000 if (m.group("k") or m.group("k2")) else 1)
        out.append(int(round(value)))
    return out


def check_output(text: str, verified_amounts: Iterable[int] = ()) -> OutputCheck:
    """Keep the reply's line structure; drop or replace only the offending sentences."""
    verified = set(verified_amounts)
    price_hits = internal_hits = 0
    lines_out: list[str] = []
    for line in text.splitlines():
        kept: list[str] = []
        for sentence in SENTENCE_END.split(line):
            if not sentence.strip():
                continue
            if INTERNAL.search(sentence):
                internal_hits += 1
                continue
            if any(a not in verified for a in amounts_in(sentence)):
                price_hits += 1
                already = PRICE_LINE in kept or (lines_out and lines_out[-1] == PRICE_LINE)
                if not already:
                    kept.append(PRICE_LINE)
                continue
            kept.append(sentence.strip())
        if kept or not line.strip():
            lines_out.append(" ".join(kept))
    cleaned = re.sub(r"\n{3,}", "\n\n", "\n".join(lines_out)).strip()
    return OutputCheck(text=cleaned, price_stripped=price_hits, internal_stripped=internal_hits)
