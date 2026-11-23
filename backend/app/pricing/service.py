"""The one public entry point of the pricing engine (plan §15 step 10).

Everything that needs a price (the chat agent's tool, the API, the CLI, the evals) calls
calculate_quote(). It is the only place that combines party -> validation -> costs -> money,
so there is exactly one way to get a number.
"""

from __future__ import annotations

from datetime import date

from app.core.config import Settings, get_settings
from app.data_loader.content_loader import ContentLibrary
from app.data_loader.rate_loader import RateBook
from app.pricing.calculator import build_costs, price_quote
from app.pricing.models import QuoteRequest, QuoteResult
from app.pricing.money import effective_margins
from app.pricing.party import build_party
from app.pricing.reasons import Refusal
from app.pricing.validators import validate


def calculate_quote(req: QuoteRequest, *, rates: RateBook | None = None,
                    content: ContentLibrary | None = None, today: date | None = None,
                    settings: Settings | None = None) -> QuoteResult:
    """Price a booking, or explain why a specialist must.

    Defaults come from get_dataset() and get_settings(); tests pass their own. "today" defaults
    to MIRA_TODAY, never the system clock.
    """
    settings = settings or get_settings()
    if rates is None or content is None:
        from app.data_loader import get_dataset
        dataset = get_dataset()
        rates = rates or dataset.rates
        content = content or dataset.content
    today = today or settings.mira_today

    def refer(*reasons: Refusal) -> QuoteResult:
        return QuoteResult(status="needs_specialist", request=req, reasons=reasons)

    party = build_party(req.adults, req.child_ages)
    if isinstance(party, Refusal):
        return refer(party)
    if refusal := validate(req, party, rates, content, today):
        return refer(refusal)

    tour = rates.tours[req.tour_id]
    build = build_costs(tour, party, req.start_date, rates)
    if isinstance(build, list):
        return refer(*build)

    margin = effective_margins(rates.settings, settings.mira_margin_day,
                               settings.mira_margin_multiday).for_kind(tour.kind)
    tour_name = content.get(req.tour_id).title
    staff = price_quote(build, tour, tour_name, req.start_date, party, rates, margin, today)
    return QuoteResult(status="ok", request=req, staff=staff)
