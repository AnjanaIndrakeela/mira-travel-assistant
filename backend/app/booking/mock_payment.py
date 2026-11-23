"""A mock payment provider (the brief says booking and payment are mocked).

No money moves and no card data is stored or logged: the card number only decides whether
the mock charge succeeds. Failures are deterministic so they can be demoed and tested:
- the test card 4000 0000 0000 0002 always fails;
- MOCK_PAYMENT_FAIL=1 makes every charge fail.
"""

from __future__ import annotations

import re
import secrets

from pydantic import BaseModel

from app.core.config import get_settings

FAIL_CARD = "4000000000000002"
SUCCESS_CARD = "4242424242424242"      # any other 12-19 digit number also succeeds


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
