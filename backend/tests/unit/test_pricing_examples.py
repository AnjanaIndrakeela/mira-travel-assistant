"""Step 4.1: every worked example in plan §15.3, end to end through calculate_quote()."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import pytest

from app.pricing import QuoteRequest, calculate_quote

TODAY = date(2026, 11, 19)


@dataclass(frozen=True)
class Example:
    tour: str
    start: date
    adults: int
    ages: tuple[int, ...]
    lines: dict[str, int | tuple[int, int]]     # item -> LKR, or (LKR, USD) for hotels
    vehicle: str
    cost_lkr: int
    cost_usd: str
    price: int
    deposit: int
    balance_due: date | None


EXAMPLES = {
    "S02": Example("T01", date(2027, 1, 10), 2, (),
                   dict(guide=9_000, vehicle=18_000, entrance=33_000, meals=6_000),
                   "Car", 66_000, "220.00", 315, 315, None),
    "S03": Example("T09", date(2027, 4, 12), 2, (7, 10),
                   dict(guide=66_500, vehicle=182_000, entrance=114_000, meals=94_500, hotels=210_000),
                   "Van", 667_000, "2223.33", 2965, 742, date(2027, 3, 13)),
    "S13a": Example("T09", date(2027, 5, 3), 2, (),
                    dict(guide=66_500, vehicle=126_000, entrance=76_000, meals=63_000, hotels=146_000),
                    "Car", 477_500, "1591.67", 2125, 532, date(2027, 4, 3)),
    "S13b": Example("T09", date(2027, 5, 3), 4, (),
                    dict(guide=66_500, vehicle=182_000, entrance=152_000, meals=126_000, hotels=292_000),
                    "Van", 818_500, "2728.33", 3640, 910, date(2027, 4, 3)),
    "S15": Example("T05", date(2027, 3, 15), 2, (1,),
                   dict(guide=5_000, vehicle=18_000, entrance=30_000, meals=4_000),
                   "Car", 57_000, "190.00", 275, 275, None),
    "Q-1044": Example("T08", date(2026, 12, 1), 2, (),
                      dict(guide=76_000, vehicle=144_000, entrance=84_000, meals=72_000, hotels=187_000),
                      "Car", 563_000, "1876.67", 2505, 2505, None),          # starts in 12 days
    "T13": Example("T13", date(2027, 5, 10), 2, (),
                   dict(guide=77_000, vehicle=126_000, entrance=90_000, meals=63_000, hotels=(44_000, 500)),
                   "Car", 400_000, "1833.33", 2445, 612, date(2027, 4, 10)),
}


@pytest.mark.parametrize("name", list(EXAMPLES))
def test_worked_example(rates, content, name):
    ex = EXAMPLES[name]
    req = QuoteRequest(tour_id=ex.tour, start_date=ex.start, adults=ex.adults, child_ages=ex.ages)
    result = calculate_quote(req, rates=rates, content=content, today=TODAY)
    assert result.status == "ok", result.reasons

    staff, public = result.staff, result.public
    got = {line.item: (line.lkr, line.usd) if line.usd else line.lkr for line in staff.cost_lines}
    assert got == ex.lines
    assert staff.vehicle == ex.vehicle
    assert staff.cost_lkr == ex.cost_lkr
    assert staff.cost_usd.quantize(Decimal("0.01")) == Decimal(ex.cost_usd)
    assert (public.price_usd, public.deposit_usd) == (ex.price, ex.deposit)
    assert public.balance_usd == ex.price - ex.deposit
    assert public.balance_due == ex.balance_due
