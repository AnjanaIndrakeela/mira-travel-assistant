"""The party (steps 3.9-3.11): adults, children 2-11, infants 0-1; bad ages are refused."""

import pytest

from app.pricing.party import Party, build_party
from app.pricing.reasons import Refusal, RefusalCode


# --- 3.9 sorting by age -----------------------------------------------------------------

def test_plan_example_two_adults_two_children_one_infant():
    assert build_party(2, [7, 10, 1]) == Party(adults=2, children=2, infants=1)


def test_age_12_counts_as_an_adult():
    assert build_party(1, [12]) == Party(adults=2, children=0, infants=0)


@pytest.mark.parametrize("age, expected", [
    (0, Party(2, 0, 1)), (1, Party(2, 0, 1)),        # infants
    (2, Party(2, 1, 0)), (11, Party(2, 1, 0)),       # children
    (12, Party(3, 0, 0)), (17, Party(3, 0, 0)),      # adults (decision a)
])
def test_age_boundaries(age, expected):
    assert build_party(2, [age]) == expected


def test_no_children():
    assert build_party(2) == Party(2, 0, 0)
    assert build_party(2, ()) == Party(2, 0, 0)


def test_zero_adults_is_left_to_the_validators():
    """no_adults is step 3.16; the party just reports the counts."""
    assert build_party(0, [5]) == Party(0, 1, 0)
    assert build_party(0, [14]) == Party(1, 0, 0)     # a 14-year-old alone counts as an adult


# --- 3.10 infants take no seat and don't count towards the limit ------------------------

def test_infants_are_excluded_from_headcount_and_travellers():
    p = build_party(2, [7, 10, 1])
    assert p.vehicle_headcount == 4 and p.travellers == 4


def test_infants_dont_change_the_vehicle_band():
    """3 adults + an infant still fits a car (Car 1-3); a fourth seated person needs a van."""
    assert build_party(3, [1]).vehicle_headcount == 3
    assert build_party(3, [2]).vehicle_headcount == 4


def test_twenty_travellers_plus_infants():
    p = build_party(18, [5, 6, 0, 1])
    assert p.travellers == 20 and p.infants == 2


# --- 3.11 invalid ages --------------------------------------------------------------------

@pytest.mark.parametrize("ages", [[-1], [18], [7, 25], [70, -3, 5]])
def test_invalid_ages_are_refused(ages):
    r = build_party(2, ages)
    assert isinstance(r, Refusal)
    assert r.code == RefusalCode.INVALID_AGE
    assert all(str(a) in r.detail_staff for a in ages)


def test_invalid_age_message_is_for_travellers():
    r = build_party(2, [25])
    assert "between 0 and 17" in r.message_traveller


def test_party_cannot_be_negative_or_changed():
    with pytest.raises(ValueError):
        Party(-1, 0, 0)
    p = Party(2, 0, 0)
    with pytest.raises(AttributeError):
        p.adults = 3
