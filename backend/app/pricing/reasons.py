"""Why a quote could not be priced (READ ME rule 11: never invent a rate).

Every "no price" answer carries one or more Refusals. Each has two texts:
- detail_staff: precise and internal (rate IDs, sheet rows, dates). Goes to staff and traces.
- message_traveller: safe to show a traveller. Never names a hotel, a missing rate, a sheet
  row or any cost. By default it is the fixed message for the code (TRAVELLER_MESSAGES).

Use `refuse(code, detail_staff)` to build one.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class RefusalCode(StrEnum):
    # request and tour checks (validators.py, party.py)
    UNKNOWN_TOUR = "unknown_tour"
    NOT_PUBLISHED = "not_published"
    STALE_TOUR = "stale_tour"
    NO_RATE_ROW = "no_rate_row"
    NO_ADULTS = "no_adults"
    GROUP_TOO_LARGE = "group_too_large"
    INVALID_AGE = "invalid_age"
    DATE_IN_PAST = "date_in_past"
    DATE_OUT_OF_RANGE = "date_out_of_range"
    # rate checks while building the cost (calculator.py)
    MISSING_RATE = "missing_rate"
    EXPIRED_RATE = "expired_rate"
    RATE_CONFLICT = "rate_conflict"
    NO_VEHICLE = "no_vehicle"
    HOTEL_NIGHT_MISMATCH = "hotel_night_mismatch"


_SPECIALIST = "A travel specialist will confirm the price for these dates and get back to you."

TRAVELLER_MESSAGES: dict[RefusalCode, str] = {
    RefusalCode.UNKNOWN_TOUR:
        "I couldn't find that tour in our current programme. A travel specialist can help you choose one.",
    RefusalCode.NOT_PUBLISHED:
        "That tour isn't open for booking yet. A travel specialist can tell you when it will be.",
    RefusalCode.STALE_TOUR:
        "That offer is no longer available. A travel specialist can suggest a current alternative.",
    RefusalCode.NO_RATE_ROW:
        "This tour is quoted individually. A travel specialist will confirm the price and get back to you.",
    RefusalCode.NO_ADULTS:
        "Every booking needs at least one adult traveller (aged 12 or over).",
    RefusalCode.GROUP_TOO_LARGE:
        "Our private tours take up to 20 travellers. Our sales team will arrange a quote for a larger group.",
    RefusalCode.INVALID_AGE:
        "Please check the children's ages: each should be between 0 and 17 (12 and over travel as adults).",
    RefusalCode.DATE_IN_PAST:
        "That start date has already passed. Please choose a future date.",
    RefusalCode.DATE_OUT_OF_RANGE:
        "We can't confirm prices that far ahead yet. " + _SPECIALIST,
    RefusalCode.MISSING_RATE: _SPECIALIST,
    RefusalCode.EXPIRED_RATE: _SPECIALIST,
    RefusalCode.RATE_CONFLICT: _SPECIALIST,
    RefusalCode.NO_VEHICLE: _SPECIALIST,
    RefusalCode.HOTEL_NIGHT_MISMATCH: _SPECIALIST,
}

# Anything that would leak internals to a traveller: rate/hotel/tour IDs, sheet rows,
# local currency amounts, cost or margin words, raw codes.
INTERNAL_DETAIL = re.compile(
    r"\b[HT]\d{2}\b|\brows?\b|\bsheet\b|\bworkbook\b|\bLKR\b|\bcost|\bmargin|\bgross profit"
    r"|\brate\b|\brates\b|\bFX\b|_",
    re.IGNORECASE,
)


class Refusal(BaseModel):
    """One reason a booking goes to a specialist instead of getting a price."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: RefusalCode
    detail_staff: str = Field(min_length=1, description="Internal detail, e.g. sheet row and rate ID")
    message_traveller: str = Field(min_length=1, description="Safe for travellers: no rates, costs or rows")

    @model_validator(mode="before")
    @classmethod
    def _default_message(cls, data: Any) -> Any:
        if isinstance(data, dict) and not data.get("message_traveller") and "code" in data:
            try:
                data = {**data, "message_traveller": TRAVELLER_MESSAGES[RefusalCode(data["code"])]}
            except ValueError:
                pass                                   # bad code: field validation reports it
        return data

    @field_validator("message_traveller")
    @classmethod
    def _no_internal_detail(cls, v: str) -> str:
        if m := INTERNAL_DETAIL.search(v):
            raise ValueError(f"traveller message reveals internal detail: {m.group(0)!r}")
        return v


def refuse(code: RefusalCode | str, detail_staff: str) -> Refusal:
    """A Refusal with the standard traveller message for its code."""
    return Refusal(code=code, detail_staff=detail_staff)
