"""Who is travelling, in the counts the pricing rules need (READ ME rules 3, 4, 5, 10).

"2 adults and kids aged 7, 10 and 1" -> 2 adults, 2 children, 1 infant.

- Age 12 and over counts as an adult (decision a; policy P03 "Children 12 and over pay adult
  rates"), so (1, [12]) is 2 adults.
- Ages 2-11 are children: child entrance fee, 50% meals, an extra bed, and a vehicle seat.
- Ages 0-1 are infants: free, no seat, no bed, not counted towards the group limit.
- An age below 0 or above 17 in child_ages is not a child at all: refused as invalid_age,
  never guessed (an 18-year-old should be entered as an adult, a typo like 70 checked).

Whether there is at least one adult (no_adults) and the group limit (group_too_large) are
checked by validators.py, using these counts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from app.pricing.reasons import Refusal, RefusalCode, refuse

ADULT_FROM_AGE = 12     # decision a
CHILD_FROM_AGE = 2      # READ ME rule 5: infants are under 2
MAX_CHILD_AGE = 17      # anything older in child_ages is a data error, not a child


@dataclass(frozen=True)
class Party:
    adults: int         # given adults + any "child" aged 12 or over
    children: int       # ages 2-11
    infants: int        # ages 0-1

    def __post_init__(self) -> None:
        if min(self.adults, self.children, self.infants) < 0:
            raise ValueError("party counts cannot be negative")

    @property
    def travellers(self) -> int:
        """Group size for the 20-traveller limit (rule 10): infants don't count."""
        return self.adults + self.children

    @property
    def vehicle_headcount(self) -> int:
        """Seats for choosing the vehicle (rule 3): infants take no seat."""
        return self.adults + self.children


def build_party(adults: int, child_ages: Iterable[int] = ()) -> Party | Refusal:
    """Sort travellers into adults, children and infants, or refuse with invalid_age."""
    ages = list(child_ages)
    bad = [a for a in ages if a < 0 or a > MAX_CHILD_AGE]
    if bad:
        return refuse(RefusalCode.INVALID_AGE,
                      f"child_ages {ages}: {bad} outside 0-{MAX_CHILD_AGE}")
    return Party(
        adults=adults + sum(a >= ADULT_FROM_AGE for a in ages),
        children=sum(CHILD_FROM_AGE <= a < ADULT_FROM_AGE for a in ages),
        infants=sum(a < CHILD_FROM_AGE for a in ages),
    )
