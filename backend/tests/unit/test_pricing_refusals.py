"""Step 4.2: the 11 refusal cases of plan §15.3. Each returns needs_specialist and NO price."""

import re
from datetime import date

import pytest

from app.pricing import QuoteRequest, RefusalCode, calculate_quote

TODAY = date(2026, 11, 19)

REFUSALS = {
    "S04 T12 solo":             ("T12", date(2027, 4, 10), 1, (), RefusalCode.MISSING_RATE),
    "S05 T11 Jan 2027":         ("T11", date(2027, 1, 20), 2, (), RefusalCode.EXPIRED_RATE),
    "S06 T10 Instafamous":      ("T10", date(2027, 2, 10), 2, (), RefusalCode.NO_RATE_ROW),
    "T16 Cultural Triangle 5n": ("T16", date(2027, 5, 3), 2, (), RefusalCode.NO_RATE_ROW),
    "T15 draft":                ("T15", date(2027, 5, 3), 2, (), RefusalCode.NOT_PUBLISHED),
    "T14 expired offer":        ("T14", date(2027, 5, 3), 2, (), RefusalCode.STALE_TOUR),
    "T09 H03 conflict Feb":     ("T09", date(2027, 2, 1), 2, (), RefusalCode.RATE_CONFLICT),
    "21 travellers":            ("T09", date(2027, 5, 3), 21, (), RefusalCode.GROUP_TOO_LARGE),
    "start before today":       ("T01", date(2026, 11, 18), 2, (), RefusalCode.DATE_IN_PAST),
    "ends after 31 Oct 2027":   ("T09", date(2027, 10, 28), 2, (), RefusalCode.DATE_OUT_OF_RANGE),
    "0 adults":                 ("T01", date(2027, 1, 10), 0, (8,), RefusalCode.NO_ADULTS),
}
PRICE_WORDS = ("price", "deposit", "balance", "cost", "margin", "gp", "usd", "lkr")


@pytest.mark.parametrize("name", list(REFUSALS))
def test_refusal(rates, content, name):
    tour, start, adults, ages, code = REFUSALS[name]
    req = QuoteRequest(tour_id=tour, start_date=start, adults=adults, child_ages=ages)
    result = calculate_quote(req, rates=rates, content=content, today=TODAY)

    assert result.status == "needs_specialist"
    assert {r.code for r in result.reasons} == {code}
    # no price anywhere in the result
    assert result.staff is None and result.public is None
    dumped = result.model_dump()
    assert set(dumped) == {"status", "request", "staff", "reasons"}
    assert not any(w in key.lower() for w in PRICE_WORDS for key in dumped["request"])
    # traveller text names no rate, hotel or code
    for reason in result.reasons:
        assert "_" not in reason.message_traveller
        assert set(re.findall(r"\d+", reason.message_traveller)) <= {"0", "12", "17", "20"}   # policy only
