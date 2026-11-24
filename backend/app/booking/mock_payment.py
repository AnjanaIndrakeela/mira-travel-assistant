"""A mock payment provider (the brief says booking and payment are mocked).

No money moves and no card data is stored or logged. The form asks for everything a real
checkout would (cardholder, card type, number, expiry, security code) and check_card tests it
the way a provider would: the Luhn checksum, the number matching the chosen card type, an
expiry date that hasn't passed and a 3-digit code (4 for American Express). Only the card type
and last four digits are kept, on the booking. Failures are deterministic so they can be demoed:
- the test card 4000 0000 0000 0002 always fails;
- MOCK_PAYMENT_FAIL=1 makes every charge fail.
"""

from __future__ import annotations

import calendar
import re
import secrets
from datetime import date
from typing import Literal

from pydantic import BaseModel

from app.core.config import get_settings

FAIL_CARD = "4000000000000002"
SUCCESS_CARD = "4242424242424242"      # any other 12-19 digit number also succeeds


Brand = Literal["visa", "mastercard", "amex"]
BRAND_NAMES: dict[str, str] = {"visa": "Visa", "mastercard": "Mastercard", "amex": "American Express"}
CardField = Literal["holder", "brand", "number", "expiry", "cvc"]


def digits_of(number: str) -> str:
    return re.sub(r"[ -]", "", number or "")


def luhn_ok(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch) * (2 if i % 2 else 1)
        total += n - 9 if n > 9 else n
    return total % 10 == 0


def brand_of(digits: str) -> Brand | None:
    """The card type a number belongs to (by its first digits and length), or None."""
    if re.fullmatch(r"4\d{12}(?:\d{3}){0,2}", digits):
        return "visa"
    if re.fullmatch(r"(?:5[1-5]\d{2}|222[1-9]|22[3-9]\d|2[3-6]\d{2}|27[01]\d|2720)\d{12}", digits):
        return "mastercard"
    if re.fullmatch(r"3[47]\d{13}", digits):
        return "amex"
    return None


def check_card(*, holder: str, brand: str, number: str, exp_month: int, exp_year: int, cvc: str,
               today: date) -> tuple[str, CardField] | None:
    """(reason, field) for the first problem, or None if the card could be charged."""
    digits = digits_of(number)
    if not re.search(r"[^\W\d_]", holder or ""):
        return "invalid_holder", "holder"
    if not re.fullmatch(r"\d{12,19}", digits) or not luhn_ok(digits):
        return "invalid_card", "number"
    if brand_of(digits) != brand:
        return "brand_mismatch", "brand"
    year = exp_year + 2000 if exp_year < 100 else exp_year
    if not 1 <= exp_month <= 12 or year > today.year + 20:
        return "invalid_expiry", "expiry"
    if date(year, exp_month, calendar.monthrange(year, exp_month)[1]) < today:
        return "card_expired", "expiry"
    if not re.fullmatch(r"\d{4}" if brand == "amex" else r"\d{3}", cvc or ""):
        return "invalid_cvc", "cvc"
    return None


class Charge(BaseModel):
    ok: bool
    reference: str | None = None       # e.g. "mock_ch_3f9a..." when ok
    reason: str | None = None          # "card_declined" | "provider_unavailable" | "invalid_card"


def charge(amount_usd: int, card_number: str, *, force_fail: bool | None = None) -> Charge:
    digits = re.sub(r"[ -]", "", card_number or "")
    if not re.fullmatch(r"\d{12,19}", digits):
        return Charge(ok=False, reason="invalid_card")
    if amount_usd <= 0:
        return Charge(ok=False, reason="invalid_amount")
    fail = get_settings().mock_payment_fail if force_fail is None else force_fail
    if fail:
        return Charge(ok=False, reason="provider_unavailable")
    if digits == FAIL_CARD:
        return Charge(ok=False, reason="card_declined")
    return Charge(ok=True, reference=f"mock_ch_{secrets.token_hex(8)}")
