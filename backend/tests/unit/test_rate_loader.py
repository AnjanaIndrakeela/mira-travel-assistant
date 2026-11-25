"""Rate loader: messy cells are parsed exactly, and gaps are never filled in."""

import inspect
from datetime import date
from decimal import Decimal

import pytest

from app.data_loader import rate_loader
from app.data_loader.rate_loader import TourKind, normalise_tour_id, parse_date, parse_money
from tests.conftest import issue_codes


# ---- helpers (2.18, 2.19, 2.22)

@pytest.mark.parametrize("raw, expected, was_text", [
    (28000, Decimal("28000"), False),
    (27.5, Decimal("27.5"), False),
    ("LKR 28,000", Decimal("28000"), True),
    ("  28,000 ", Decimal("28000"), True),
    (None, None, False),
    ("", None, False),
])
def test_parse_money(raw, expected, was_text):
    assert parse_money(raw) == (expected, was_text)


@pytest.mark.parametrize("raw", ["about 20k", "N/A", True])
def test_parse_money_refuses_to_guess(raw):
    with pytest.raises(ValueError):
        parse_money(raw)


def test_parse_date_is_day_first():
    assert parse_date("15/12/2026") == (date(2026, 12, 15), True)
    assert parse_date("01/02/2027") == (date(2027, 2, 1), True)   # 1 Feb, not 2 Jan
    with pytest.raises(ValueError):
        parse_date("next week")


@pytest.mark.parametrize("raw, expected", [("T-13", "T13"), ("T13", "T13"), ("t1", "T01")])
def test_normalise_tour_id(raw, expected):
    assert normalise_tour_id(raw) == expected


# ---- read-only (2.17)

def test_workbook_is_opened_read_only_and_never_saved():
    source = inspect.getsource(rate_loader)
    assert "read_only=True" in source and "data_only=True" in source
    assert ".save(" not in source


# ---- settings, seasons, vehicles (2.23, 2.24)

def test_settings(rates):
    s = rates.settings
    assert s.fx_lkr_per_usd == 300
    assert s.fx_fixed_until == date(2027, 10, 31)
    assert (s.margin_day, s.margin_multiday) == (Decimal("0.3"), Decimal("0.25"))
    assert s.deposit_multiday == Decimal("0.25")
    assert s.full_payment_within_days == 30
    assert s.max_group_size == 20
    assert s.round_up_to_usd == 5


def test_seasons_cover_the_quoting_year(rates):
    assert rates.seasons[0].valid_from == date(2026, 11, 1)
    assert rates.seasons[-1].valid_to == date(2027, 10, 31)


@pytest.mark.parametrize("headcount, vehicle", [
    (1, "Car"), (3, "Car"), (4, "Van"), (8, "Van"), (9, "Mini coach"), (20, "Mini coach"),
])
def test_vehicle_by_group_size(rates, headcount, vehicle):
    assert rates.vehicle_for(headcount).name == vehicle


def test_no_vehicle_beyond_20(rates):
    assert rates.vehicle_for(21) is None


# ---- tours

def test_tours(rates):
    assert sorted(rates.tours) == ["T01", "T02", "T03", "T04", "T05", "T06", "T07", "T08",
                                   "T09", "T11", "T12", "T13", "T14", "T15"]
    t09 = rates.tours["T09"]
    assert (t09.kind, t09.days, t09.nights) == (TourKind.MULTI_DAY, 7, 6)
    assert t09.hotel_ids_by_night == ("H12", "H12", "H02", "H02", "H03", "H03")
    assert rates.tours["T01"].kind is TourKind.DAY
    assert rates.tours["T01"].hotel_ids_by_night == ()


def test_t13_id_is_normalised(rates):
    assert rates.tours["T13"].source_id == "T-13"
    assert len(issue_codes(rates.issues, "inconsistent_tour_id")) == 1


# ---- hotels (2.18-2.21, 2.25)

def test_text_price_is_parsed(rates):
    h02 = rates.hotel_rates_for("H02", date(2026, 11, 20))
    assert [h.double_room for h in h02] == [Decimal("28000")]
    assert len(issue_codes(rates.issues, "text_price")) == 2


def test_text_date_is_parsed(rates):
    peak = rates.hotel_rates_for("H08", date(2026, 12, 15))
    assert [h.season for h in peak] == ["Peak"]
    assert len(issue_codes(rates.issues, "text_date")) == 1


def test_usd_rows_keep_their_currency(rates):
    h10 = rates.hotel_rates_for("H10", date(2027, 5, 10))
    assert [(h.currency, h.double_room) for h in h10] == [("USD", Decimal("125"))]
    assert all(h.currency == "LKR" for h in rates.hotels if h.hotel_id != "H10")


def test_missing_rate_stays_none(rates):
    h04 = [h for h in rates.hotels if h.hotel_id == "H04"]
    assert len(h04) == 4 and all(h.single_room is None for h in h04)
    assert all(h.double_room is not None for h in h04)
    assert len(issue_codes(rates.issues, "missing_rate")) == 4


def test_overlapping_rows_are_a_conflict(rates):
    rows = rates.hotel_rates_for("H03", date(2027, 2, 1))
    assert sorted(h.row for h in rows) == [13, 56]
    assert rates.hotel_rates_for("H03", date(2026, 12, 20))[0].row == 13   # before the overlap
    [conflict] = issue_codes(rates.issues, "rate_conflict")
    assert "2027-01-01..2027-03-31" in conflict.detail


def test_expired_hotel_has_no_rate_in_the_quoting_year(rates):
    assert rates.hotel_rates_for("H07", date(2027, 1, 20)) == []
    [expired] = issue_codes(rates.issues, "expired_rate")
    assert "H07" in expired.detail


def test_every_tour_hotel_exists_and_matches_nights(rates):
    assert not issue_codes(rates.issues, "unknown_hotel")
    assert not issue_codes(rates.issues, "hotel_night_mismatch")
