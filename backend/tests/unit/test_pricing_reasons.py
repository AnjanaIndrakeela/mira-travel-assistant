"""Refusal reasons (step 3.8): every code has a safe traveller message; staff detail stays internal."""

import re

import pytest
from pydantic import ValidationError

from app.pricing.reasons import INTERNAL_DETAIL, TRAVELLER_MESSAGES, Refusal, RefusalCode, refuse

PLAN_CODES = {  # plan §15, step 2
    "unknown_tour", "not_published", "stale_tour", "no_rate_row", "no_adults", "group_too_large",
    "invalid_age", "date_in_past", "date_out_of_range", "missing_rate", "expired_rate",
    "rate_conflict", "no_vehicle", "hotel_night_mismatch",
}


def test_codes_match_the_plan():
    assert {c.value for c in RefusalCode} == PLAN_CODES


def test_code_from_text():
    assert RefusalCode("missing_rate") is RefusalCode.MISSING_RATE
    with pytest.raises(ValueError):
        RefusalCode("too_expensive")


def test_every_code_has_a_traveller_message():
    assert set(TRAVELLER_MESSAGES) == set(RefusalCode)
    assert all(m.strip() for m in TRAVELLER_MESSAGES.values())


@pytest.mark.parametrize("code", list(RefusalCode))
def test_traveller_messages_have_no_internal_detail(code):
    msg = TRAVELLER_MESSAGES[code]
    assert not INTERNAL_DETAIL.search(msg), msg
    assert code.value not in msg
    # only public policy numbers: ages 0-17, adults from 12, max 20 travellers; never an amount
    assert set(re.findall(r"\d+", msg)) <= {"0", "12", "17", "20"}, msg


@pytest.mark.parametrize("code", list(RefusalCode))
def test_refuse_uses_the_standard_message(code):
    r = refuse(code, "detail for staff")
    assert r.code == code and r.message_traveller == TRAVELLER_MESSAGES[code]


def test_staff_detail_keeps_internal_facts():
    r = refuse("missing_rate", "H04 Heritance Tea Factory has no single-room rate for 2027-04-16 (Hotels!row 18)")
    assert "H04" in r.detail_staff and "row 18" in r.detail_staff
    assert "H04" not in r.message_traveller


@pytest.mark.parametrize("leak", [
    "H04 has no single rate for that night.",
    "See Hotels row 18.",
    "The cost is LKR 210,000.",
    "Our margin is too thin.",
    "Reason: missing_rate",
    "Tour T09 is not available.",
])
def test_a_leaky_traveller_message_is_rejected(leak):
    with pytest.raises(ValidationError, match="internal detail"):
        Refusal(code="missing_rate", detail_staff="x", message_traveller=leak)


def test_custom_safe_message_is_allowed():
    r = Refusal(code="date_in_past", detail_staff="start 2026-11-01 < today 2026-11-19",
                message_traveller="That date has passed. Could you pick another?")
    assert r.message_traveller.startswith("That date")


@pytest.mark.parametrize("bad", [
    dict(code="nope", detail_staff="x"),
    dict(code="missing_rate", detail_staff=""),
    dict(code="missing_rate", detail_staff="x", price_usd=100),
])
def test_bad_refusals_are_rejected(bad):
    with pytest.raises(ValidationError):
        Refusal(**bad)


def test_refusal_is_immutable():
    r = refuse("no_adults", "adults=0")
    with pytest.raises(ValidationError):
        r.code = RefusalCode.UNKNOWN_TOUR
