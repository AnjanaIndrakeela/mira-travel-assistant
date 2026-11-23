"""Cost build-up (steps 3.20-3.28) against the real workbook and plan §15.3."""

from datetime import date
from decimal import Decimal

import pytest

from app.pricing.calculator import CostBuild, Rooms, build_costs
from app.pricing.party import Party, build_party
from app.pricing.reasons import RefusalCode

# case: (tour, start, adults, child_ages, guide, vehicle name, vehicle, entrance, meals, hotels LKR, hotels USD)
EXAMPLES = {
    "S02":   ("T01", date(2027, 1, 10), 2, (), 9_000, "Car", 18_000, 33_000, 6_000, None, 0),
    "S03":   ("T09", date(2027, 4, 12), 2, (7, 10), 66_500, "Van", 182_000, 114_000, 94_500, 210_000, 0),
    "S13a":  ("T09", date(2027, 5, 3), 2, (), 66_500, "Car", 126_000, 76_000, 63_000, 146_000, 0),
    "S13b":  ("T09", date(2027, 5, 3), 4, (), 66_500, "Van", 182_000, 152_000, 126_000, 292_000, 0),
    "S15":   ("T05", date(2027, 3, 15), 2, (1,), 5_000, "Car", 18_000, 30_000, 4_000, None, 0),
    "Q1044": ("T08", date(2026, 12, 1), 2, (), 76_000, "Car", 144_000, 84_000, 72_000, 187_000, 0),
    "T13":   ("T13", date(2027, 5, 10), 2, (), 77_000, "Car", 126_000, 90_000, 63_000, 44_000, 500),
}
COST_LKR = {"S02": 66_000, "S03": 667_000, "S13a": 477_500, "S13b": 818_500,
            "S15": 57_000, "Q1044": 563_000, "T13": 400_000}


def build(rates, tour_id, start, adults, ages=()):
    return build_costs(rates.tours[tour_id], build_party(adults, ages), start, rates)


def lines(b: CostBuild) -> dict:
    return {line.item: line for line in b.lines}


@pytest.mark.parametrize("case", list(EXAMPLES))
def test_worked_examples(rates, case):
    tour, start, adults, ages, guide, vname, vehicle, entrance, meals, h_lkr, h_usd = EXAMPLES[case]
    b = build(rates, tour, start, adults, ages)
    assert isinstance(b, CostBuild), b
    got = lines(b)
    assert got["guide"].lkr == guide                       # 3.20
    assert (b.vehicle, got["vehicle"].lkr) == (vname, vehicle)   # 3.21
    assert got["entrance"].lkr == entrance                 # 3.22
    assert got["meals"].lkr == meals                       # 3.23
    if h_lkr is None:
        assert "hotels" not in got                         # day tour
    else:
        assert (got["hotels"].lkr, got["hotels"].usd) == (h_lkr, h_usd)   # 3.24, 3.28
    assert b.cost_lkr == COST_LKR[case]
    assert b.usd_parts == h_usd


def test_lines_follow_rule_2_order(rates):
    b = build(rates, "T09", date(2027, 4, 12), 2, (7, 10))
    assert [line.item for line in b.lines] == ["guide", "vehicle", "entrance", "meals", "hotels"]


def test_detail_text_is_readable(rates):
    got = lines(build(rates, "T09", date(2027, 4, 12), 2, (7, 10)))
    assert got["vehicle"].detail == "Van 26,000 × 7 days"
    assert got["entrance"].detail == "38,000 × 2 adults + 19,000 × 2 children"
    assert got["meals"].detail == "4,500 × 7 days × (2 adults + 0.5 × 2 children)"
    assert got["hotels"].detail == "6 nights, 1 double + 2 extra beds per night"
    assert lines(build(rates, "T01", date(2027, 1, 10), 2))["guide"].detail == "9,000 × 1 day"


# 3.22 entrance is whole tour, not per day ---------------------------------------------------

def test_entrance_is_not_multiplied_by_days(rates):
    t = rates.tours["T09"]
    got = lines(build(rates, "T09", date(2027, 4, 12), 2))
    assert got["entrance"].lkr == t.entrance_adult_lkr * 2
    assert got["entrance"].lkr != t.entrance_adult_lkr * 2 * t.days


def test_infants_pay_nothing(rates):
    with_infant = build(rates, "T09", date(2027, 4, 12), 2, (1,))
    without = build(rates, "T09", date(2027, 4, 12), 2)
    assert with_infant.cost_lkr == without.cost_lkr


# 3.24 night 1 = start date; rate rows recorded ------------------------------------------------

def test_s03_night_table(rates):
    b = build(rates, "T09", date(2027, 4, 12), 2, (7, 10))
    hotel_rows = [r for r in b.rate_rows if r.startswith("Hotels!")]
    assert hotel_rows[0] == "Hotels!row 50 (H12 Shoulder) 2027-04-12"
    assert hotel_rows[2] == "Hotels!row 10 (H02 Shoulder) 2027-04-14"
    assert hotel_rows[5] == "Hotels!row 14 (H03 Shoulder) 2027-04-17"
    assert len(hotel_rows) == 6
    assert b.rate_rows[:2] == ("Tours!row 10 (T09)", "Transport (Van)")


# 3.25 rooms -------------------------------------------------------------------------------

@pytest.mark.parametrize("party, rooms", [
    (Party(2, 0, 0), Rooms(1, 0, 0)),
    (Party(1, 0, 0), Rooms(0, 1, 0)),
    (Party(3, 0, 0), Rooms(1, 1, 0)),
    (Party(4, 2, 1), Rooms(2, 0, 2)),          # infant: no bed
    (Party(1, 1, 0), Rooms(0, 1, 1)),
])
def test_rooms(party, rooms):
    assert Rooms.for_party(party) == rooms


def test_odd_adult_pays_a_single(rates):
    three = lines(build(rates, "T09", date(2027, 5, 3), 3))["hotels"].lkr
    two = lines(build(rates, "T09", date(2027, 5, 3), 2))["hotels"].lkr
    assert three > two


# 3.26 refusals -----------------------------------------------------------------------------

def test_s04_solo_on_t12_has_no_single_rate_at_h04(rates):
    problems = build(rates, "T12", date(2027, 4, 10), 1)
    assert isinstance(problems, list)
    assert [p.code for p in problems] == [RefusalCode.MISSING_RATE]
    assert "H04" in problems[0].detail_staff and "single room" in problems[0].detail_staff
    assert "H04" not in problems[0].message_traveller


def test_couple_on_t12_does_not_need_the_missing_single_rate(rates):
    b = build(rates, "T12", date(2027, 4, 10), 2)
    assert isinstance(b, CostBuild)


def test_s05_expired_h07(rates):
    problems = build(rates, "T11", date(2027, 1, 20), 2)
    assert {p.code for p in problems} == {RefusalCode.EXPIRED_RATE}
    assert "2026-10-31" in problems[0].detail_staff


def test_t09_february_rate_conflict_on_h03(rates):
    problems = build(rates, "T09", date(2027, 2, 1), 2)
    assert [p.code for p in problems] == [RefusalCode.RATE_CONFLICT] * 2
    assert all("H03" in p.detail_staff for p in problems)
    assert "night 5" in problems[0].detail_staff and "night 6" in problems[1].detail_staff


# 3.27 collect ALL problems -------------------------------------------------------------------

def test_every_expired_night_is_listed(rates):
    problems = build(rates, "T11", date(2027, 1, 20), 2)
    assert len(problems) == 6
    assert [f"night {i}" in p.detail_staff for i, p in enumerate(problems, 1)] == [True] * 6


def test_vehicle_and_hotel_problems_are_reported_together(rates):
    no_car = rates.model_copy(update={"vehicles": [v for v in rates.vehicles if v.name != "Car"]})
    problems = build(no_car, "T11", date(2027, 1, 20), 2)
    assert {p.code for p in problems} == {RefusalCode.NO_VEHICLE, RefusalCode.EXPIRED_RATE}
    assert len(problems) == 7


# 3.28 USD rows ----------------------------------------------------------------------------

def test_t13_usd_hotel_rows_are_kept_in_usd(rates):
    b = build(rates, "T13", date(2027, 5, 10), 2)
    h = lines(b)["hotels"]
    assert (h.lkr, h.usd) == (Decimal(44_000), Decimal(500))
    assert b.cost_lkr == 400_000 and b.usd_parts == 500
    assert "USD 500" in h.detail
