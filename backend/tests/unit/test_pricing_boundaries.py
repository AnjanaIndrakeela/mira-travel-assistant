"""Step 4.3: the edges where one more person or one more day changes the answer."""

from datetime import date, timedelta

import pytest

from app.pricing import QuoteRequest, calculate_quote

TODAY = date(2026, 11, 19)


def quote(rates, content, tour, start, adults, ages=(), today=TODAY):
    req = QuoteRequest(tour_id=tour, start_date=start, adults=adults, child_ages=ages)
    r = calculate_quote(req, rates=rates, content=content, today=today)
    assert r.status == "ok", r.reasons
    return r


# age 12 = adult (decision a; P03) -------------------------------------------------------------

def test_age_12_pays_as_an_adult(rates, content):
    with_12 = quote(rates, content, "T09", date(2027, 5, 3), 2, (12,))
    three_adults = quote(rates, content, "T09", date(2027, 5, 3), 3)
    assert with_12.public.price_usd == three_adults.public.price_usd == 2960
    assert (with_12.public.adults, with_12.public.children) == (3, 0)


def test_age_11_is_still_a_child(rates, content):
    r = quote(rates, content, "T09", date(2027, 5, 3), 2, (11,))
    assert (r.public.adults, r.public.children) == (2, 1)
    assert r.public.price_usd < 2960


# vehicle bands (rule 3): Car 1-3, Van 4-8, Mini coach 9-20 -------------------------------------

@pytest.mark.parametrize("adults, ages, vehicle", [
    (3, (), "Car"), (4, (), "Van"),
    (2, (5,), "Car"), (2, (5, 6), "Van"),          # children take seats
    (3, (1,), "Car"),                               # infants don't
    (8, (), "Van"), (9, (), "Mini coach"),
    (7, (6, 9), "Mini coach"), (20, (), "Mini coach"),
])
def test_vehicle_bands(rates, content, adults, ages, vehicle):
    assert quote(rates, content, "T01", date(2027, 1, 10), adults, ages).staff.vehicle == vehicle


def test_car_to_van_changes_the_price(rates, content):
    three = quote(rates, content, "T01", date(2027, 1, 10), 3).staff
    four = quote(rates, content, "T01", date(2027, 1, 10), 4).staff
    vehicle = lambda s: next(line.lkr for line in s.cost_lines if line.item == "vehicle")
    assert (vehicle(three), vehicle(four)) == (18_000, 26_000)


# deposit: within 30 days pays in full (decision b: <= 30) ---------------------------------------

@pytest.mark.parametrize("days_ahead, full", [(29, True), (30, True), (31, False)])
def test_thirty_day_deposit_boundary(rates, content, days_ahead, full):
    start = TODAY + timedelta(days=days_ahead)
    p = quote(rates, content, "T09", start, 2).public
    assert (p.deposit_usd == p.price_usd) is full
    if not full:
        assert p.deposit_usd == -(-p.price_usd * 25 // 100)          # ceil 25 %
        assert p.balance_due == start - timedelta(days=30)


# group limit: 20 travellers, infants not counted ------------------------------------------------

def test_twenty_travellers_plus_an_infant_is_allowed(rates, content):
    assert quote(rates, content, "T01", date(2027, 1, 10), 19, (5, 1)).public.infants == 1
