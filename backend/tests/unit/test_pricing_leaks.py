"""Step 4.5: what a traveller (or the LLM) can see never contains cost, margin or gross profit."""

import json
from datetime import date

import pytest

from app.pricing import PublicQuote, QuoteRequest, calculate_quote

TODAY = date(2026, 11, 19)
CASES = [("T01", date(2027, 1, 10), 2, ()), ("T09", date(2027, 4, 12), 2, (7, 10)),
         ("T13", date(2027, 5, 10), 2, ()), ("T08", date(2026, 12, 1), 2, ())]
INTERNAL_WORDS = ("cost", "margin", "gp", "profit", "lkr", "fx", "rate", "row", "vehicle")


@pytest.mark.parametrize("case", CASES, ids=[c[0] for c in CASES])
def test_public_quote_dump_has_no_internal_numbers(rates, content, case):
    tour, start, adults, ages = case
    r = calculate_quote(QuoteRequest(tour_id=tour, start_date=start, adults=adults, child_ages=ages),
                        rates=rates, content=content, today=TODAY)
    public = r.public.model_dump(mode="json")

    assert not [k for k in public if any(w in k.lower() for w in INTERNAL_WORDS)]
    text = json.dumps(public)
    staff = r.staff
    secrets = {str(staff.cost_lkr), f"{staff.cost_usd:.2f}", str(staff.gp_pct), str(staff.margin),
               *(str(line.lkr) for line in staff.cost_lines), staff.vehicle, *staff.rate_rows}
    assert not [s for s in secrets if s and s in text]


def test_public_quote_schema_has_no_internal_fields():
    """Field names and field descriptions (what an LLM tool schema would expose)."""
    props = PublicQuote.model_json_schema()["properties"]
    text = json.dumps(props).lower()
    for word in ("cost", "margin", "gp_pct", "profit", "lkr", "rate_rows"):
        assert word not in text
