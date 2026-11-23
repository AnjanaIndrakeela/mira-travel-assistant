"""The cost build-up (READ ME rules 2-6): what the booking costs us, in LKR (+ USD hotel rows).

Runs only after validators.py has passed. Never guesses: a hotel night with no covering row,
two covering rows, or an empty rate cell we need becomes a Refusal, and EVERY such problem
across all nights is collected (rule 11) so staff see the full picture in one hand-off.

price_quote() then applies the money rules (money.py) to give the StaffQuote.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from app.data_loader.rate_loader import HotelRate, RateBook, TourKind, TourRate
from app.pricing.models import CostLine, PublicQuote, StaffQuote, gross_profit_pct
from app.pricing.money import apply_margin, ceil_usd, lkr_to_usd, round_up_to
from app.pricing.party import Party
from app.pricing.reasons import Refusal, RefusalCode, refuse

CHILD_MEAL_SHARE = Decimal("0.5")      # rule 5: children pay 50% of the adult meal cost


@dataclass(frozen=True)
class CostBuild:
    """The cost of one booking, before margin. Becomes part of the StaffQuote."""

    lines: tuple[CostLine, ...]
    vehicle: str
    rate_rows: tuple[str, ...]

    @property
    def cost_lkr(self) -> Decimal:
        return sum((line.lkr for line in self.lines), Decimal(0))

    @property
    def usd_parts(self) -> Decimal:
        """USD-contracted hotel rows (decision e: never converted by FX)."""
        return sum((line.usd for line in self.lines), Decimal(0))


def _n(amount: Decimal) -> str:
    """12345 -> '12,345'; 4500.50 -> '4,500.50'."""
    return f"{amount:,.2f}".removesuffix(".00")


def _days(n: int) -> str:
    return f"{n} day" if n == 1 else f"{n} days"


# ------------------------------------------------------------- guide, vehicle, entrance, meals

def guide_line(tour: TourRate) -> CostLine:
    return CostLine(item="guide", lkr=tour.guide_lkr_per_day * tour.days,
                    detail=f"{_n(tour.guide_lkr_per_day)} × {_days(tour.days)}")


def entrance_line(tour: TourRate, party: Party) -> CostLine:
    """Whole tour, per person: NOT multiplied by days."""
    lkr = tour.entrance_adult_lkr * party.adults + tour.entrance_child_lkr * party.children
    detail = f"{_n(tour.entrance_adult_lkr)} × {party.adults} adults"
    if party.children:
        detail += f" + {_n(tour.entrance_child_lkr)} × {party.children} children"
    return CostLine(item="entrance", lkr=lkr, detail=detail)


def meals_line(tour: TourRate, party: Party) -> CostLine:
    people = party.adults + CHILD_MEAL_SHARE * party.children
    detail = f"{_n(tour.meals_lkr_per_adult_per_day)} × {_days(tour.days)} × ({party.adults} adults"
    detail += f" + 0.5 × {party.children} children)" if party.children else ")"
    return CostLine(item="meals", lkr=tour.meals_lkr_per_adult_per_day * tour.days * people, detail=detail)


# ------------------------------------------------------------- hotels, night by night

@dataclass(frozen=True)
class Rooms:
    """Rule 4: two adults share a double, an odd adult takes a single, each child an extra bed."""

    doubles: int
    singles: int
    extra_beds: int

    @classmethod
    def for_party(cls, party: Party) -> "Rooms":
        return cls(doubles=party.adults // 2, singles=party.adults % 2, extra_beds=party.children)

    def describe(self) -> str:
        parts = [(self.doubles, "double"), (self.singles, "single"), (self.extra_beds, "extra bed")]
        return " + ".join(f"{n} {name}{'s' if n > 1 else ''}" for n, name in parts if n)


def _row_ref(row: HotelRate, night: date) -> str:
    return f"Hotels!row {row.row} ({row.hotel_id} {row.season}) {night.isoformat()}"


def hotel_nights(tour: TourRate, party: Party, start: date, rates: RateBook
                 ) -> tuple[CostLine | None, list[str], list[Refusal]]:
    """Price every night (night 1 = start date). Returns (line, rate rows, ALL problems)."""
    if not tour.hotel_ids_by_night:
        return None, [], []                    # day tour: no hotel

    rooms = Rooms.for_party(party)
    lkr, usd = Decimal(0), Decimal(0)
    rows_used: list[str] = []
    problems: list[Refusal] = []

    for i, hotel_id in enumerate(tour.hotel_ids_by_night):
        night = start + timedelta(days=i)
        where = f"{hotel_id} {rates.hotel_name(hotel_id)}, night {i + 1} ({night.isoformat()})"
        rows = rates.hotel_rates_for(hotel_id, night)

        if not rows:
            known = [h for h in rates.hotels if h.hotel_id == hotel_id]
            span = (f"rows cover {min(h.valid_from for h in known)} to {max(h.valid_to for h in known)}"
                    if known else "no rows on the Hotels tab")
            problems.append(refuse(RefusalCode.EXPIRED_RATE, f"{where}: no rate covers this night; {span}"))
            continue
        if len(rows) > 1:
            refs = ", ".join(f"row {r.row} ({r.season} {r.valid_from} to {r.valid_to})" for r in rows)
            problems.append(refuse(RefusalCode.RATE_CONFLICT, f"{where}: {len(rows)} rows cover this night: {refs}"))
            continue

        row = rows[0]
        needed = [("double room", rooms.doubles, row.double_room),
                  ("single room", rooms.singles, row.single_room),
                  ("child extra bed", rooms.extra_beds, row.extra_bed_child)]
        missing = [name for name, count, rate in needed if count and rate is None]
        if missing:                            # only demand rates this party actually needs
            problems.append(refuse(RefusalCode.MISSING_RATE,
                                   f"{where}: no {' / '.join(missing)} rate (Hotels!row {row.row})"))
            continue

        night_cost = sum((count * rate for _, count, rate in needed if count), Decimal(0))
        if row.currency == "USD":
            usd += night_cost                  # decision e: kept in USD, never divided by FX
        else:
            lkr += night_cost
        rows_used.append(_row_ref(row, night))

    if problems:
        return None, rows_used, problems
    nights = len(tour.hotel_ids_by_night)
    detail = f"{nights} night{'s' if nights > 1 else ''}, {rooms.describe()} per night"
    if usd:
        detail += f" (USD {_n(usd)} from USD-contracted rows)"
    return CostLine(item="hotels", lkr=lkr, usd=usd, detail=detail), rows_used, []


# ------------------------------------------------------------- the whole build-up

def build_costs(tour: TourRate, party: Party, start: date, rates: RateBook) -> CostBuild | list[Refusal]:
    """Rule 2: guide + vehicle + entrance + meals + hotels. Returns every problem, or the build."""
    problems: list[Refusal] = []

    vehicle = rates.vehicle_for(party.vehicle_headcount)    # rule 3: infants take no seat
    if vehicle is None:
        problems.append(refuse(RefusalCode.NO_VEHICLE,
                               f"no vehicle on the Transport tab for {party.vehicle_headcount} travellers"))

    hotels, hotel_rows, hotel_problems = hotel_nights(tour, party, start, rates)
    problems += hotel_problems
    if problems:
        return problems

    lines = [
        guide_line(tour),
        CostLine(item="vehicle", lkr=vehicle.lkr_per_day * tour.days,
                 detail=f"{vehicle.name} {_n(vehicle.lkr_per_day)} × {_days(tour.days)}"),
        entrance_line(tour, party),
        meals_line(tour, party),
    ]
    if hotels is not None:
        lines.append(hotels)
    rows = (f"Tours!row {tour.row} ({tour.tour_id})", f"Transport ({vehicle.name})", *hotel_rows)
    return CostBuild(lines=tuple(lines), vehicle=vehicle.name, rate_rows=rows)


# ------------------------------------------------------------- price, deposit, gross profit

def price_quote(build: CostBuild, tour: TourRate, tour_name: str, start: date, party: Party,
                rates: RateBook, margin: Decimal, today: date) -> StaffQuote:
    """Rules 7-9 on top of the cost build-up. Only the final total and the deposit are rounded."""
    s = rates.settings
    cost_usd = lkr_to_usd(build.cost_lkr, s.fx_lkr_per_usd) + build.usd_parts       # exact (decision d)
    price = round_up_to(apply_margin(cost_usd, margin), s.round_up_to_usd)          # rules 7, 8

    days_to_start = (start - today).days
    if tour.kind is TourKind.DAY or days_to_start <= s.full_payment_within_days:  # decision b: <= 30
        deposit, balance_due = price, None
    else:                                                                           # decision c: rounded price
        deposit = ceil_usd(Decimal(price) * s.deposit_multiday)
        balance_due = start - timedelta(days=s.full_payment_within_days)

    public = PublicQuote(
        tour_id=tour.tour_id, tour_name=tour_name, start_date=start,
        end_date=start + timedelta(days=tour.days - 1),
        adults=party.adults, children=party.children, infants=party.infants,
        price_usd=price, deposit_usd=deposit, balance_usd=price - deposit, balance_due=balance_due)
    return StaffQuote(
        public=public, cost_lines=build.lines, fx_lkr_per_usd=s.fx_lkr_per_usd,
        cost_lkr=build.cost_lkr, cost_usd=cost_usd, margin=margin,
        gp_pct=gross_profit_pct(price, cost_usd), vehicle=build.vehicle, rate_rows=build.rate_rows)
