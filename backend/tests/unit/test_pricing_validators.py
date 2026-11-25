"""Validation before any arithmetic (steps 3.12-3.19), against the real dataset."""

from datetime import date

import pytest

from app.pricing.models import QuoteRequest
from app.pricing.party import Party, build_party
from app.pricing.reasons import RefusalCode
from app.pricing.validators import last_quotable_day, last_tour_day, validate

TODAY = date(2026, 11, 19)          # MIRA_TODAY for the evals


def check(rates, content, tour_id="T09", start=date(2027, 4, 12), adults=2, ages=(7, 10), today=TODAY):
    req = QuoteRequest(tour_id=tour_id, start_date=start, adults=adults, child_ages=ages)
    party = build_party(req.adults, req.child_ages)
    return validate(req, party, rates, content, today)


def code(result):
    return result.code if result else None


@pytest.mark.parametrize("tour_id, start", [
    ("T09", date(2027, 4, 12)),     # S03
    ("T01", date(2027, 1, 10)),     # S02 day tour
    ("T13", date(2027, 5, 3)),
])
def test_bookable_tours_pass(rates, content, tour_id, start):
    assert check(rates, content, tour_id, start) is None


# 3.12 - 3.15: the tour ---------------------------------------------------------------------

@pytest.mark.parametrize("tour_id", ["T99", "X1", "P03"])     # P03 exists but is a policy
def test_unknown_tour(rates, content, tour_id):
    r = check(rates, content, tour_id)
    assert code(r) == RefusalCode.UNKNOWN_TOUR


def test_draft_tour_is_not_published(rates, content):
    assert code(check(rates, content, "T15")) == RefusalCode.NOT_PUBLISHED


def test_expired_offer_is_stale(rates, content):
    r = check(rates, content, "T14")
    assert code(r) == RefusalCode.STALE_TOUR
    assert "T14" in r.detail_staff and "T14" not in r.message_traveller


@pytest.mark.parametrize("tour_id", ["T10", "T16"])
def test_tour_without_rate_row(rates, content, tour_id):
    assert code(check(rates, content, tour_id)) == RefusalCode.NO_RATE_ROW


def test_hotel_night_mismatch(rates, content):
    broken = rates.model_copy(update={"tours": {
        **rates.tours, "T09": rates.tours["T09"].model_copy(update={"nights": 7})}})
    r = check(broken, content)
    assert code(r) == RefusalCode.HOTEL_NIGHT_MISMATCH
    assert "Tours!row" in r.detail_staff


# 3.16 - 3.17: the party --------------------------------------------------------------------

def test_no_adults(rates, content):
    assert code(check(rates, content, adults=0, ages=(7,))) == RefusalCode.NO_ADULTS


def test_teenager_counts_as_the_adult(rates, content):
    assert check(rates, content, adults=0, ages=(14, 7)) is None


def test_twenty_travellers_is_the_limit(rates, content):
    assert check(rates, content, adults=20, ages=()) is None
    assert check(rates, content, adults=18, ages=(5, 6, 0, 1)) is None     # infants don't count


def test_twenty_one_is_too_large(rates, content):
    r = check(rates, content, adults=21, ages=())
    assert code(r) == RefusalCode.GROUP_TOO_LARGE
    assert code(check(rates, content, adults=19, ages=(5, 6))) == RefusalCode.GROUP_TOO_LARGE


def test_no_vehicle_for_headcount(rates, content):
    no_coach = rates.model_copy(update={"vehicles": [v for v in rates.vehicles if v.max_travellers <= 8]})
    assert code(check(no_coach, content, adults=12, ages=())) == RefusalCode.NO_VEHICLE


# 3.18 - 3.19: the dates --------------------------------------------------------------------

def test_start_before_today(rates, content):
    assert code(check(rates, content, start=date(2026, 11, 18))) == RefusalCode.DATE_IN_PAST


def test_start_today_is_allowed(rates, content):
    assert check(rates, content, "T01", start=TODAY) is None


def test_today_is_a_parameter(rates, content):
    assert check(rates, content, start=date(2027, 4, 12), today=date(2027, 4, 13)) is not None
    assert check(rates, content, start=date(2027, 4, 12), today=date(2027, 4, 12)) is None


def test_last_quotable_day_is_31_oct_2027(rates):
    assert last_quotable_day(rates) == date(2027, 10, 31)


def test_tour_ending_on_31_oct_is_allowed(rates, content):
    start = date(2027, 10, 25)                       # T09: 7 days, 25-31 Oct
    assert last_tour_day(start, rates.tours["T09"]) == date(2027, 10, 31)
    assert check(rates, content, start=start) is None


def test_tour_running_past_31_oct_is_out_of_range(rates, content):
    r = check(rates, content, start=date(2027, 10, 26))      # ends 1 Nov 2027
    assert code(r) == RefusalCode.DATE_OUT_OF_RANGE
    assert "2027-11-01" in r.detail_staff


def test_day_tour_after_the_fx_date(rates, content):
    assert check(rates, content, "T01", start=date(2027, 10, 31)) is None
    assert code(check(rates, content, "T01", start=date(2027, 11, 1))) == RefusalCode.DATE_OUT_OF_RANGE


# order: the first failing check wins -------------------------------------------------------

def test_tour_checks_come_before_party_and_dates(rates, content):
    r = check(rates, content, "T15", start=date(2020, 1, 1), adults=30, ages=())
    assert code(r) == RefusalCode.NOT_PUBLISHED


def test_party_checks_come_before_dates(rates, content):
    r = check(rates, content, start=date(2020, 1, 1), adults=21, ages=())
    assert code(r) == RefusalCode.GROUP_TOO_LARGE


def test_validate_never_uses_the_system_clock():
    import inspect
    import app.pricing.validators as v
    assert "date.today" not in inspect.getsource(v) and "datetime.now" not in inspect.getsource(v)


def test_party_is_used_as_given(rates, content):
    req = QuoteRequest(tour_id="T09", start_date=date(2027, 4, 12), adults=2)
    assert code(validate(req, Party(0, 0, 0), rates, content, TODAY)) == RefusalCode.NO_ADULTS
