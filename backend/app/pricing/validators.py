"""Checks before any arithmetic: refuse early and clearly (plan §15 step 4).

The checks run in a fixed order and the FIRST failure is the reason. Tour checks come first,
so a traveller asking for a draft or withdrawn tour is told that, not "too many people".
Rate problems found night by night (missing / expired / conflicting hotel rates) are not
checked here: calculator.py collects all of them.

"today" is always a parameter, never the system clock, so evals are reproducible.
"""

from __future__ import annotations

from datetime import date, timedelta

from app.data_loader.content_loader import ContentLibrary, has_expired_season
from app.data_loader.rate_loader import RateBook, TourRate
from app.pricing.models import QuoteRequest
from app.pricing.party import Party
from app.pricing.reasons import Refusal, RefusalCode, refuse


def last_tour_day(start: date, tour: TourRate) -> date:
    """Day 1 is the start date, so a 7-day tour from 12 Apr ends on 18 Apr."""
    return start + timedelta(days=tour.days - 1)


def last_quotable_day(rates: RateBook) -> date:
    """Rule 1: FX is fixed for quoting until this date; no season runs past it either."""
    season_end = max((s.valid_to for s in rates.seasons), default=rates.settings.fx_fixed_until)
    return min(rates.settings.fx_fixed_until, season_end)


def validate(req: QuoteRequest, party: Party, rates: RateBook, content: ContentLibrary,
             today: date) -> Refusal | None:
    """Return the first reason this booking can't be priced, or None if it may go on."""
    tid = req.tour_id

    # 1-4: the tour itself
    doc = content.get(tid)
    if doc is None or doc.type != "tour":
        return refuse(RefusalCode.UNKNOWN_TOUR, f"{tid!r} is not a tour in the content library")
    if not doc.is_published:
        return refuse(RefusalCode.NOT_PUBLISHED, f"{tid} {doc.title!r} has status {doc.status!r} ({doc.path})")
    if has_expired_season(f"{doc.title}\n{doc.body}", today):
        return refuse(RefusalCode.STALE_TOUR, f"{tid} {doc.title!r} is an offer for a season that has ended")
    tour = rates.tours.get(tid)
    if tour is None:
        return refuse(RefusalCode.NO_RATE_ROW, f"{tid} {doc.title!r} has no row on the Tours tab")

    # 5: the rate row is internally consistent
    if tour.days < 1 or tour.nights != len(tour.hotel_ids_by_night):
        return refuse(RefusalCode.HOTEL_NIGHT_MISMATCH,
                      f"{tid} (Tours!row {tour.row}): {tour.days} days, {tour.nights} nights, "
                      f"{len(tour.hotel_ids_by_night)} hotel entries")

    # 6-8: the party (rules 3 and 10)
    if party.adults < 1:
        return refuse(RefusalCode.NO_ADULTS, f"party has no adult: {party}")
    limit = rates.settings.max_group_size
    if party.travellers > limit:
        return refuse(RefusalCode.GROUP_TOO_LARGE,
                      f"{party.travellers} travellers (infants excluded) > maximum {limit}")
    if rates.vehicle_for(party.vehicle_headcount) is None:
        return refuse(RefusalCode.NO_VEHICLE, f"no vehicle on the Transport tab for {party.vehicle_headcount}")

    # 9-10: the dates (rule 1)
    if req.start_date < today:
        return refuse(RefusalCode.DATE_IN_PAST, f"start {req.start_date} is before today {today}")
    end, limit_day = last_tour_day(req.start_date, tour), last_quotable_day(rates)
    if end > limit_day:
        return refuse(RefusalCode.DATE_OUT_OF_RANGE,
                      f"{tid} runs {req.start_date} to {end}; rates and FX are fixed only until {limit_day}")
    return None
