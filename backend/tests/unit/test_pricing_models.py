"""Pricing data shapes: malformed requests are rejected; business limits are left to refusals."""

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.pricing.models import (CostLine, PublicQuote, QuoteRequest, QuoteResult, StaffQuote,
                                gross_profit_pct)
from app.pricing.reasons import Refusal, RefusalCode

START = date(2027, 4, 12)


def test_valid_request():
    req = QuoteRequest(tour_id="T09", start_date=START, adults=2, child_ages=[7, 10])
    assert (req.tour_id, req.start_date, req.adults, req.child_ages) == ("T09", START, 2, (7, 10))


def test_child_ages_default_to_none():
    assert QuoteRequest(tour_id="T01", start_date=START, adults=2).child_ages == ()


def test_negative_adults_rejected():
    with pytest.raises(ValidationError):
        QuoteRequest(tour_id="T01", start_date=START, adults=-1)


@pytest.mark.parametrize("bad", [2.5, True, "2", None])
def test_adults_must_be_a_real_integer(bad):
    with pytest.raises(ValidationError):
        QuoteRequest(tour_id="T01", start_date=START, adults=bad)


@pytest.mark.parametrize("bad", [[7.5], [True], ["7"]])
def test_child_ages_must_be_integers(bad):
    with pytest.raises(ValidationError):
        QuoteRequest(tour_id="T01", start_date=START, adults=2, child_ages=bad)


def test_business_limits_are_not_validation_errors():
    # 0 adults, 25 people, odd ages, past dates: well-formed, refused later with a reason code.
    QuoteRequest(tour_id="T01", start_date=date(2020, 1, 1), adults=0)
    QuoteRequest(tour_id="T01", start_date=START, adults=25, child_ages=[25, -1])


@pytest.mark.parametrize("raw, expected", [("T-13", "T13"), (" t09 ", "T09"), ("T9", "T09"),
                                           ("XYZ", "XYZ")])
def test_tour_id_is_normalised(raw, expected):
    assert QuoteRequest(tour_id=raw, start_date=START, adults=1).tour_id == expected


@pytest.mark.parametrize("bad", ["", "   "])
def test_empty_tour_id_rejected(bad):
    with pytest.raises(ValidationError):
        QuoteRequest(tour_id=bad, start_date=START, adults=1)


def test_bad_date_rejected():
    with pytest.raises(ValidationError):
        QuoteRequest(tour_id="T01", start_date="next Friday", adults=2)


def test_missing_fields_rejected():
    with pytest.raises(ValidationError):
        QuoteRequest(tour_id="T01", adults=2)


def test_unknown_fields_rejected():
    # No hidden inputs: a discount (or anything else) cannot be passed to the engine.
    with pytest.raises(ValidationError):
        QuoteRequest(tour_id="T01", start_date=START, adults=2, discount=0.5)


def test_request_is_immutable():
    req = QuoteRequest(tour_id="T01", start_date=START, adults=2)
    with pytest.raises(ValidationError):
        req.adults = 5


# ---- CostLine (3.4)


def test_cost_line_builds():
    line = CostLine(item="vehicle", lkr=Decimal("182000"), detail="Van 26,000 × 7 days")
    assert (line.item, line.lkr, line.usd) == ("vehicle", Decimal("182000"), Decimal(0))


def test_cost_line_accepts_int_and_numeric_text():
    assert CostLine(item="guide", lkr=9000, detail="x").lkr == Decimal("9000")
    assert CostLine(item="guide", lkr="9000.50", detail="x").lkr == Decimal("9000.50")


def test_usd_hotel_line():
    # T13: LKR hotels plus the USD-contracted Cinnamon Wild Yala (H10), kept apart.
    line = CostLine(item="hotels", lkr=Decimal("44000"), usd=Decimal("500"), detail="2 LKR + 4 USD nights")
    assert (line.lkr, line.usd) == (Decimal("44000"), Decimal("500"))


@pytest.mark.parametrize("field", ["lkr", "usd"])
def test_floats_are_rejected(field):
    with pytest.raises(ValidationError, match="never float"):
        CostLine(item="hotels", detail="x", **{field: 0.1})


@pytest.mark.parametrize("field", ["lkr", "usd"])
def test_negative_amounts_rejected(field):
    with pytest.raises(ValidationError):
        CostLine(item="hotels", detail="x", **{field: Decimal("-1")})


def test_usd_only_on_hotel_lines():
    with pytest.raises(ValidationError, match="only hotel"):
        CostLine(item="meals", usd=Decimal("10"), detail="x")


@pytest.mark.parametrize("item", ["discount", "supplement", "tax", ""])
def test_only_the_five_readme_cost_items(item):
    with pytest.raises(ValidationError):
        CostLine(item=item, lkr=1, detail="x")


def test_cost_line_needs_a_detail_and_no_extras():
    with pytest.raises(ValidationError):
        CostLine(item="guide", lkr=1, detail="")
    with pytest.raises(ValidationError):
        CostLine(item="guide", lkr=1, detail="x", margin=0.3)


def test_cost_line_is_immutable():
    line = CostLine(item="guide", lkr=1, detail="x")
    with pytest.raises(ValidationError):
        line.lkr = Decimal(2)


# ---- PublicQuote (3.5)

S03 = dict(  # T09, 2 adults + children 7 and 10, from 12 Apr 2027 (plan §15.3)
    tour_id="T09", tour_name="Cultural Triangle Sri Lanka Package",
    start_date=date(2027, 4, 12), end_date=date(2027, 4, 18),
    adults=2, children=2, infants=0,
    price_usd=2965, deposit_usd=742, balance_usd=2223, balance_due=date(2027, 3, 13))

S02 = dict(  # T01 day tour, 2 adults, 10 Jan 2027: paid in full
    tour_id="T01", tour_name="Sigiriya and Minneriya Day Tour from Kandy",
    start_date=date(2027, 1, 10), end_date=date(2027, 1, 10),
    adults=2, children=0, infants=0,
    price_usd=315, deposit_usd=315, balance_usd=0, balance_due=None)


def test_public_quote_builds():
    q = PublicQuote(**S03)
    assert (q.price_usd, q.deposit_usd, q.balance_usd, q.currency) == (2965, 742, 2223, "USD")
    assert PublicQuote(**S02).balance_due is None


def test_public_quote_has_no_cost_fields():
    """Travellers and the LLM only ever get PublicQuote: it must not be able to carry costs."""
    forbidden = ("cost", "margin", "gp", "profit", "lkr", "rate", "fx")
    leaks = [f for f in PublicQuote.model_fields if any(w in f.lower() for w in forbidden)]
    assert leaks == []


def test_public_quote_json_has_no_cost_words():
    text = PublicQuote(**S03).model_dump_json().lower()
    assert not any(w in text for w in ("cost", "margin", "gp_", "profit", "lkr"))


def test_cost_fields_cannot_be_added():
    with pytest.raises(ValidationError):
        PublicQuote(**S03, cost_usd=2223.33)
    with pytest.raises(ValidationError):
        PublicQuote(**S03, margin=0.25)


@pytest.mark.parametrize("change, message", [
    (dict(deposit_usd=3000, balance_usd=-35), "deposit|balance|greater"),
    (dict(balance_usd=2000), "price minus deposit"),
    (dict(balance_due=None), "balance_due is set"),
    (dict(balance_due=date(2027, 4, 12)), "before the start"),
    (dict(end_date=date(2027, 4, 11)), "end_date"),
])
def test_impossible_quotes_are_rejected(change, message):
    with pytest.raises(ValidationError, match=message):
        PublicQuote(**{**S03, **change})


def test_paid_in_full_has_no_balance_due():
    with pytest.raises(ValidationError, match="balance_due is set"):
        PublicQuote(**{**S02, "balance_due": date(2026, 12, 11)})


@pytest.mark.parametrize("field, bad", [("price_usd", 2965.0), ("price_usd", 0), ("adults", 0),
                                        ("deposit_usd", 0), ("currency", "LKR")])
def test_field_limits(field, bad):
    with pytest.raises(ValidationError):
        PublicQuote(**{**S03, field: bad})


# ---- StaffQuote (3.6)

FX = Decimal("300")

S03_LINES = (  # plan §15.3: T09, 2 adults + children 7 and 10, from 12 Apr 2027
    CostLine(item="guide", lkr=Decimal("66500"), detail="9,500 × 7 days"),
    CostLine(item="vehicle", lkr=Decimal("182000"), detail="Van 26,000 × 7 days"),
    CostLine(item="entrance", lkr=Decimal("114000"), detail="38,000 × 2 adults + 19,000 × 2 children"),
    CostLine(item="meals", lkr=Decimal("94500"), detail="4,500 × 7 days × (2 + 0.5 × 2)"),
    CostLine(item="hotels", lkr=Decimal("210000"), detail="6 nights, 1 double + 2 extra beds"),
)


def _staff_s03(**change):
    cost_usd = Decimal("667000") / FX
    values = dict(public=PublicQuote(**S03), cost_lines=S03_LINES, fx_lkr_per_usd=FX,
                  cost_lkr=Decimal("667000"), cost_usd=cost_usd, margin=Decimal("0.25"),
                  gp_pct=gross_profit_pct(2965, cost_usd), vehicle="Van",
                  rate_rows=("Tours!row 10 (T09)", "Transport!row 3 (Van)",
                             "Hotels!row 50 (H12 Shoulder) 2027-04-12"))
    return StaffQuote(**{**values, **change})


def test_staff_quote_builds_for_s03():
    q = _staff_s03()
    assert q.cost_lkr == 667000
    assert q.cost_usd.quantize(Decimal("0.01")) == Decimal("2223.33")
    assert q.gp_pct == Decimal("25.01")
    assert q.public.price_usd == 2965


def test_gross_profit_examples():
    assert gross_profit_pct(315, Decimal("220")) == Decimal("30.16")                    # S02
    assert gross_profit_pct(2965, Decimal("667000") / FX) == Decimal("25.01")           # S03


def test_usd_hotel_parts_are_added_without_fx():
    # T13 (plan §15.3): LKR 400,000 + USD 500 -> cost USD 1,833.33, price 2,445
    lines = (CostLine(item="guide", lkr=Decimal("77000"), detail="x"),
             CostLine(item="vehicle", lkr=Decimal("126000"), detail="x"),
             CostLine(item="entrance", lkr=Decimal("90000"), detail="x"),
             CostLine(item="meals", lkr=Decimal("63000"), detail="x"),
             CostLine(item="hotels", lkr=Decimal("44000"), usd=Decimal("500"), detail="x"))
    cost_usd = Decimal("400000") / FX + Decimal("500")
    public = PublicQuote(tour_id="T13", tour_name="Wildlife Photography Tour",
                         start_date=date(2027, 5, 10), end_date=date(2027, 5, 16),
                         adults=2, children=0, infants=0, price_usd=2445, deposit_usd=612,
                         balance_usd=1833, balance_due=date(2027, 4, 10))
    q = StaffQuote(public=public, cost_lines=lines, fx_lkr_per_usd=FX, cost_lkr=Decimal("400000"),
                   cost_usd=cost_usd, margin=Decimal("0.25"), gp_pct=gross_profit_pct(2445, cost_usd),
                   vehicle="Car", rate_rows=("Tours!row 13 (T13)",))
    assert q.cost_usd.quantize(Decimal("0.01")) == Decimal("1833.33")


@pytest.mark.parametrize("change, message", [
    (dict(cost_lkr=Decimal("603000")), "sum of the cost lines"),          # Q-1043's wrong total
    (dict(cost_usd=Decimal("2223.33")), "cost_lkr / FX"),                  # rounded too early (decision d)
    (dict(gp_pct=Decimal("25.00")), "gp_pct"),
    (dict(cost_lines=S03_LINES + (S03_LINES[0],)), "only once"),
])
def test_inconsistent_staff_quotes_are_rejected(change, message):
    with pytest.raises(ValidationError, match=message):
        _staff_s03(**change)


def test_price_below_cost_is_rejected():
    cheap = PublicQuote(**{**S03, "price_usd": 2000, "deposit_usd": 500, "balance_usd": 1500})
    with pytest.raises(ValidationError, match="below cost"):
        _staff_s03(public=cheap)


@pytest.mark.parametrize("field, bad", [("margin", Decimal("1")), ("margin", Decimal("-0.1")),
                                        ("margin", 0.25), ("fx_lkr_per_usd", Decimal("0")),
                                        ("vehicle", ""), ("rate_rows", ()), ("cost_lines", ())])
def test_staff_field_limits(field, bad):
    with pytest.raises(ValidationError):
        _staff_s03(**{field: bad})


def test_staff_quote_rejects_extra_fields():
    with pytest.raises(ValidationError):
        _staff_s03(discount=Decimal("0.1"))


# --- QuoteResult (step 3.7): a price or a hand-off, never both ---------------------------

S03_REQ = QuoteRequest(tour_id="T09", start_date=START, adults=2, child_ages=(7, 10))
MISSING = Refusal(code=RefusalCode.MISSING_RATE,
                  detail_staff="H04 has no single-room rate for 2027-04-16 (Hotels!row 18)",
                  message_traveller="A travel specialist will confirm the price for these dates.")


def test_ok_result_exposes_the_public_quote():
    r = QuoteResult(status="ok", request=S03_REQ, staff=_staff_s03())
    assert r.reasons == ()
    assert r.public.price_usd == 2965 and r.public.deposit_usd == 742


def test_needs_specialist_result_has_no_price():
    r = QuoteResult(status="needs_specialist", request=S03_REQ, reasons=[MISSING])
    assert r.staff is None and r.public is None
    assert r.reasons[0].code == "missing_rate"


def test_several_reasons_are_kept():
    other = MISSING.model_copy(update={"detail_staff": "H04 single, 2027-04-17 (Hotels!row 18)"})
    r = QuoteResult(status="needs_specialist", request=S03_REQ, reasons=[MISSING, other])
    assert len(r.reasons) == 2


@pytest.mark.parametrize("kwargs, message", [
    (dict(status="ok", staff="S", reasons=[MISSING]), "cannot have refusal reasons"),
    (dict(status="ok"), "needs a priced quote"),
    (dict(status="needs_specialist"), "needs at least one reason"),
    (dict(status="needs_specialist", staff="S", reasons=[MISSING]), "cannot carry a price"),
    (dict(status="maybe", staff="S"), "status"),
])
def test_impossible_results_are_rejected(kwargs, message):
    if kwargs.get("staff") == "S":
        kwargs["staff"] = _staff_s03()
    with pytest.raises(ValidationError, match=message):
        QuoteResult(request=S03_REQ, **kwargs)


@pytest.mark.parametrize("change", [dict(tour_id="T01"), dict(start_date=date(2027, 4, 13))])
def test_quote_must_match_the_request(change):
    req = S03_REQ.model_copy(update=change)
    with pytest.raises(ValidationError, match="must match the request"):
        QuoteResult(status="ok", request=req, staff=_staff_s03())


def test_result_is_immutable_and_closed():
    r = QuoteResult(status="needs_specialist", request=S03_REQ, reasons=[MISSING])
    with pytest.raises(ValidationError):
        r.status = "ok"
    with pytest.raises(ValidationError):
        QuoteResult(status="needs_specialist", request=S03_REQ, reasons=[MISSING], price_usd=100)


def test_needs_specialist_json_has_no_money():
    r = QuoteResult(status="needs_specialist", request=S03_REQ, reasons=[MISSING])
    dumped = r.model_dump()
    assert dumped["staff"] is None
    assert set(dumped) == {"status", "request", "staff", "reasons"}
    assert set(dumped["reasons"][0]) == {"code", "detail_staff", "message_traveller"}
