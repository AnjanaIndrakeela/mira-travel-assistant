"""Money rules (steps 3.29-3.35): USD, margin, round-up, deposit, balance date, GP%."""

from datetime import date
from decimal import Decimal

import pytest

from app.data_loader.rate_loader import TourKind
from app.pricing.calculator import build_costs, price_quote
from app.pricing.money import (Margins, apply_margin, ceil_usd, effective_margins, lkr_to_usd,
                               round_up_to)
from app.pricing.party import build_party

TODAY = date(2026, 11, 19)
D = Decimal


# 3.29 lkr_to_usd ---------------------------------------------------------------------------

def test_lkr_to_usd_is_exact():
    assert lkr_to_usd(D(66_000), D(300)) == 220
    assert lkr_to_usd(D(667_000), D(300)).quantize(D("0.0001")) == D("2223.3333")
    assert lkr_to_usd(D(667_000), D(300)) != D("2223.33")            # not rounded to cents


@pytest.mark.parametrize("bad", [66000.0, "66000", None, True])
def test_money_helpers_refuse_floats_and_text(bad):
    with pytest.raises(TypeError):
        lkr_to_usd(bad, D(300))


def test_fx_must_be_positive():
    with pytest.raises(ValueError):
        lkr_to_usd(D(1), D(0))


# 3.30 apply_margin -------------------------------------------------------------------------

def test_margin_is_on_the_selling_price_not_a_markup():
    sell = apply_margin(D(220), D("0.30"))
    assert sell.quantize(D("0.0001")) == D("314.2857")
    assert sell != D(220) * D("1.30")                                # 286 would be wrong
    assert ((sell - 220) / sell).quantize(D("0.0001")) == D("0.3000")      # 30% of the selling price


@pytest.mark.parametrize("bad", [D(1), D("1.5"), D("-0.1")])
def test_impossible_margins_rejected(bad):
    with pytest.raises(ValueError):
        apply_margin(D(220), bad)


# 3.31 round_up_to / ceil_usd ---------------------------------------------------------------

@pytest.mark.parametrize("amount, expected", [
    (D("314.2857"), 315), (D("315"), 315), (D("315.0001"), 320), (D("0.01"), 5), (D("2964.44"), 2965),
])
def test_round_up_to_5(amount, expected):
    assert round_up_to(amount, 5) == expected


@pytest.mark.parametrize("amount, expected", [(D("741.25"), 742), (D("742"), 742), (D("611.25"), 612)])
def test_ceil_usd(amount, expected):
    assert ceil_usd(amount) == expected


# 3.32 margins: workbook values, env override ----------------------------------------------

def test_workbook_margins(rates):
    m = effective_margins(rates.settings)
    assert m == Margins(day=D("0.3"), multiday=D("0.25"))
    assert m.for_kind(TourKind.DAY) == D("0.3") and m.for_kind(TourKind.MULTI_DAY) == D("0.25")


def test_override_changes_only_its_margin(rates):
    m = effective_margins(rates.settings, day_override=D("0.32"))
    assert m == Margins(day=D("0.32"), multiday=D("0.25"))


def test_bad_override_is_a_config_error(rates):
    with pytest.raises(ValueError):
        effective_margins(rates.settings, multiday_override=D("1"))
    with pytest.raises(TypeError):
        effective_margins(rates.settings, day_override=0.32)


def test_env_override_reaches_the_margins(rates, monkeypatch):
    from app.core.config import Settings
    monkeypatch.setenv("MIRA_MARGIN_DAY", "0.32")
    s = Settings()
    m = effective_margins(rates.settings, s.mira_margin_day, s.mira_margin_multiday)
    assert m.day == D("0.32")


# 3.33 - 3.35 end to end on the worked examples ---------------------------------------------

def quote(rates, tour_id, start, adults, ages=(), margins=None, today=TODAY):
    tour = rates.tours[tour_id]
    party = build_party(adults, ages)
    build = build_costs(tour, party, start, rates)
    margin = (margins or effective_margins(rates.settings)).for_kind(tour.kind)
    return price_quote(build, tour, tour.name, start, party, rates, margin, today)


# case: tour, start, adults, ages, cost USD (2 dp), price, deposit, balance_due
EXAMPLES = {
    "S02":   ("T01", date(2027, 1, 10), 2, (), "220.00", 315, 315, None),
    "S03":   ("T09", date(2027, 4, 12), 2, (7, 10), "2223.33", 2965, 742, date(2027, 3, 13)),
    "S13a":  ("T09", date(2027, 5, 3), 2, (), "1591.67", 2125, 532, date(2027, 4, 3)),
    "S13b":  ("T09", date(2027, 5, 3), 4, (), "2728.33", 3640, 910, date(2027, 4, 3)),
    "S15":   ("T05", date(2027, 3, 15), 2, (1,), "190.00", 275, 275, None),
    "Q1044": ("T08", date(2026, 12, 1), 2, (), "1876.67", 2505, 2505, None),     # starts in 12 days
    "T13":   ("T13", date(2027, 5, 10), 2, (), "1833.33", 2445, 612, date(2027, 4, 10)),
}


@pytest.mark.parametrize("case", list(EXAMPLES))
def test_worked_example_prices(rates, case):
    tour, start, adults, ages, cost_usd, price, deposit, due = EXAMPLES[case]
    q = quote(rates, tour, start, adults, ages)
    assert q.cost_usd.quantize(D("0.01")) == D(cost_usd)
    p = q.public
    assert (p.price_usd, p.deposit_usd, p.balance_usd, p.balance_due) == (price, deposit, price - deposit, due)


def test_s03_full_public_quote(rates):
    p = quote(rates, "T09", date(2027, 4, 12), 2, (7, 10)).public
    assert (p.tour_id, p.end_date, p.adults, p.children, p.infants) == ("T09", date(2027, 4, 18), 2, 2, 0)
    assert (p.balance_usd, p.balance_due) == (2223, date(2027, 3, 13))


@pytest.mark.parametrize("case, gp", [("S02", "30.16"), ("S03", "25.01")])
def test_gross_profit_on_the_rounded_price(rates, case, gp):
    tour, start, adults, ages, *_ = EXAMPLES[case]
    assert quote(rates, tour, start, adults, ages).gp_pct == D(gp)


def test_margin_override_s02_becomes_325(rates):
    q = quote(rates, "T01", date(2027, 1, 10), 2, margins=effective_margins(rates.settings, D("0.32")))
    assert q.public.price_usd == 325 and q.margin == D("0.32")


@pytest.mark.parametrize("days_ahead, paid_in_full", [(29, True), (30, True), (31, False)])
def test_full_payment_within_30_days(rates, days_ahead, paid_in_full):
    """Decision b: 'within 30 days' means 30 days or fewer."""
    start = date(2027, 4, 12)
    today = date.fromordinal(start.toordinal() - days_ahead)
    p = quote(rates, "T09", start, 2, (7, 10), today=today).public
    assert (p.deposit_usd == p.price_usd) is paid_in_full
    assert (p.balance_due is None) is paid_in_full


def test_day_tour_is_paid_in_full_even_months_ahead(rates):
    p = quote(rates, "T01", date(2027, 6, 1), 2).public
    assert p.deposit_usd == p.price_usd and p.balance_due is None


def test_usd_part_is_not_divided_by_fx(rates):
    q = quote(rates, "T13", date(2027, 5, 10), 2)
    assert q.cost_usd == D(400_000) / 300 + 500
