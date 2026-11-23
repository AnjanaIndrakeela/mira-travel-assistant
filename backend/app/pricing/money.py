"""The money rules (READ ME rules 1, 7, 8, 9), each one small function. Decimal only.

- Nothing is rounded until the very end (decision d): the cost stays exact, e.g. 2,223.333...
- Margin is gross profit on the selling price, not a mark-up:
      220 / (1 - 0.30) = 314.29   (right)      220 x 1.30 = 286   (wrong)
- The total is rounded UP to the next USD 5; a deposit UP to the next whole USD.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal

from app.data_loader.rate_loader import RateSettings, TourKind


def _decimal(value, name: str) -> Decimal:
    if isinstance(value, float) or not isinstance(value, (Decimal, int)) or isinstance(value, bool):
        raise TypeError(f"{name} must be Decimal or int, got {type(value).__name__}")
    return Decimal(value)


def lkr_to_usd(lkr: Decimal, fx: Decimal) -> Decimal:
    """Rule 1. Exact: 66,000 / 300 = 220; 667,000 / 300 = 2,223.333..."""
    lkr, fx = _decimal(lkr, "lkr"), _decimal(fx, "fx")
    if fx <= 0:
        raise ValueError("FX rate must be positive")
    return lkr / fx


def apply_margin(cost: Decimal, margin: Decimal) -> Decimal:
    """Rule 7. Sell = Cost / (1 - margin): 220 at 30% -> 314.2857..."""
    cost, margin = _decimal(cost, "cost"), _decimal(margin, "margin")
    check_margin(margin)
    return cost / (Decimal(1) - margin)


def round_up_to(amount: Decimal, step: int) -> int:
    """Rule 8. 314.29 -> 315; 315 -> 315; 315.0001 -> 320."""
    amount = _decimal(amount, "amount")
    if not isinstance(step, int) or step <= 0:
        raise ValueError("step must be a positive whole number")
    return int((amount / step).to_integral_value(rounding=ROUND_CEILING) * step)


def ceil_usd(amount: Decimal) -> int:
    """Rule 9 deposit. 741.25 -> 742; 742 -> 742."""
    return int(_decimal(amount, "amount").to_integral_value(rounding=ROUND_CEILING))


def check_margin(margin: Decimal) -> Decimal:
    if not Decimal(0) <= margin < Decimal(1):
        raise ValueError(f"margin must be at least 0 and below 1, got {margin}")
    return margin


# ------------------------------------------------------------- which margin applies

@dataclass(frozen=True)
class Margins:
    day: Decimal
    multiday: Decimal

    def for_kind(self, kind: TourKind) -> Decimal:
        return self.day if kind is TourKind.DAY else self.multiday


def effective_margins(rate_settings: RateSettings, day_override: Decimal | None = None,
                      multiday_override: Decimal | None = None) -> Margins:
    """Workbook Settings (30% day, 25% multi-day), unless MIRA_MARGIN_DAY / _MULTIDAY is set.

    A bad override is a configuration error, so it raises instead of quietly pricing wrong.
    """
    day = rate_settings.margin_day if day_override is None else _decimal(day_override, "day margin")
    multi = (rate_settings.margin_multiday if multiday_override is None
             else _decimal(multiday_override, "multi-day margin"))
    return Margins(day=check_margin(day), multiday=check_margin(multi))
