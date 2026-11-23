"""Load the sales team's rate workbook into typed, validated rate tables.

The workbook is opened read-only (openpyxl read_only=True, data_only=True) and never saved.
Messy cells are fixed in memory and logged as DataIssues:
- money stored as text ("LKR 28,000"), dates stored as text ("15/12/2026"),
- hotel rows in USD, missing rates (kept as None, never 0),
- overlapping rows for the same hotel, hotels whose rates have all expired,
- inconsistent tour IDs ("T-13").
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from enum import Enum
from pathlib import Path
from typing import Literal

from openpyxl import load_workbook
from pydantic import BaseModel, Field

from app.data_loader.issues import DataIssue

WORKBOOK_PATH = Path("rates") / "rate_sheet_2026-27.xlsx"
HOTELS_HEADER_ROW = 3   # the Hotels tab has a title line and a blank line before its header

_MONEY_TEXT = re.compile(r"^\s*(?:LKR|USD|Rs\.?)?\s*([\d,]+(?:\.\d+)?)\s*$", re.IGNORECASE)
_TOUR_ID = re.compile(r"^T-?(\d+)$", re.IGNORECASE)
_FX_UNTIL = re.compile(r"until\s+(\d{1,2}\s+\w{3,9}\s+\d{4})", re.IGNORECASE)


class TourKind(str, Enum):
    DAY = "day"
    MULTI_DAY = "multi_day"


class RateSettings(BaseModel, frozen=True):
    fx_lkr_per_usd: Decimal
    fx_fixed_until: date
    margin_day: Decimal
    margin_multiday: Decimal
    deposit_multiday: Decimal
    full_payment_within_days: int
    max_group_size: int
    round_up_to_usd: int


class Season(BaseModel, frozen=True):
    name: str
    valid_from: date
    valid_to: date


class TourRate(BaseModel, frozen=True):
    tour_id: str                    # normalised, e.g. "T13"
    source_id: str                  # as written in the workbook, e.g. "T-13"
    name: str
    kind: TourKind
    days: int
    nights: int
    guide_lkr_per_day: Decimal
    entrance_adult_lkr: Decimal     # per person, whole tour
    entrance_child_lkr: Decimal     # per child aged 2-11, whole tour
    meals_lkr_per_adult_per_day: Decimal
    hotel_ids_by_night: tuple[str, ...]
    notes: str | None
    row: int


class HotelRate(BaseModel, frozen=True):
    hotel_id: str
    hotel_name: str
    season: str
    valid_from: date
    valid_to: date
    currency: Literal["LKR", "USD"]
    double_room: Decimal | None     # None = no rate in the workbook (never treat as 0)
    single_room: Decimal | None
    extra_bed_child: Decimal | None
    notes: str | None
    row: int

    def covers(self, night: date) -> bool:
        return self.valid_from <= night <= self.valid_to


class Vehicle(BaseModel, frozen=True):
    name: str
    min_travellers: int
    max_travellers: int
    lkr_per_day: Decimal


class RateBook(BaseModel):
    settings: RateSettings
    seasons: list[Season]
    tours: dict[str, TourRate]
    hotels: list[HotelRate]
    vehicles: list[Vehicle]
    issues: list[DataIssue] = Field(default_factory=list)

    def hotel_rates_for(self, hotel_id: str, night: date) -> list[HotelRate]:
        """Every row for this hotel whose dates cover the night (0, 1 or, in a conflict, 2+)."""
        return [h for h in self.hotels if h.hotel_id == hotel_id and h.covers(night)]

    def hotel_name(self, hotel_id: str) -> str:
        return next((h.hotel_name for h in self.hotels if h.hotel_id == hotel_id), hotel_id)

    def vehicle_for(self, headcount: int) -> Vehicle | None:
        return next((v for v in self.vehicles
                     if v.min_travellers <= headcount <= v.max_travellers), None)


# ---------------------------------------------------------------- cell parsing helpers

def parse_money(value) -> tuple[Decimal | None, bool]:
    """Return (amount, was_text). Empty cells give (None, False). Never guesses."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None, False
    if isinstance(value, bool):
        raise ValueError(f"not a money value: {value!r}")
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value)), False
    m = _MONEY_TEXT.match(str(value))
    if not m:
        raise ValueError(f"not a money value: {value!r}")
    try:
        return Decimal(m.group(1).replace(",", "")), True
    except InvalidOperation as e:
        raise ValueError(f"not a money value: {value!r}") from e


def parse_date(value) -> tuple[date, bool]:
    """Return (date, was_text). Text dates are day-first (dd/mm/yyyy), as Sales writes them."""
    if isinstance(value, datetime):
        return value.date(), False
    if isinstance(value, date):
        return value, False
    text = str(value).strip()
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(text, fmt).date(), True
        except ValueError:
            continue
    raise ValueError(f"not a date: {value!r}")


def normalise_tour_id(raw) -> str:
    m = _TOUR_ID.match(str(raw).strip())
    if not m:
        raise ValueError(f"not a tour id: {raw!r}")
    return f"T{int(m.group(1)):02d}"


def _rows(ws, header_row: int = 1) -> list[tuple[int, dict]]:
    """[(sheet row number, {header: value})] for non-empty rows below the header."""
    all_rows = list(ws.iter_rows(values_only=True))
    headers = [str(h).strip() if h is not None else "" for h in all_rows[header_row - 1]]
    out = []
    for n, values in enumerate(all_rows[header_row:], start=header_row + 1):
        if any(v is not None and str(v).strip() for v in values):
            out.append((n, dict(zip(headers, values))))
    return out


def _col(row: dict, prefix: str):
    """Value of the first column whose header starts with prefix (headers carry units)."""
    for key, value in row.items():
        if key.lower().startswith(prefix.lower()):
            return value
    raise KeyError(prefix)


# ---------------------------------------------------------------- tabs

def _load_settings(ws) -> RateSettings:
    values: dict[str, tuple] = {}
    for _, r in _rows(ws):
        values[str(r["Setting"]).strip().lower()] = (r["Value"], r.get("Notes"))

    def get(prefix: str):
        return next(v for k, v in values.items() if k.startswith(prefix.lower()))

    fx, fx_note = get("FX rate")
    until = _FX_UNTIL.search(str(fx_note or ""))
    if not until:
        raise ValueError("Settings: FX 'fixed until' date not found in the notes")
    return RateSettings(
        fx_lkr_per_usd=Decimal(str(fx)),
        fx_fixed_until=datetime.strptime(until.group(1), "%d %b %Y").date(),
        margin_day=Decimal(str(get("Margin – day")[0])),
        margin_multiday=Decimal(str(get("Margin – multi-day")[0])),
        deposit_multiday=Decimal(str(get("Deposit – multi-day")[0])),
        full_payment_within_days=int(get("Full payment")[0]),
        max_group_size=int(get("Max group")[0]),
        round_up_to_usd=int(get("Round booking total")[0]),
    )


def _load_seasons(ws) -> list[Season]:
    return [Season(name=str(r["Season"]).strip(), valid_from=parse_date(r["From"])[0],
                   valid_to=parse_date(r["To"])[0]) for _, r in _rows(ws)]


def _load_tours(ws, issues: list[DataIssue]) -> dict[str, TourRate]:
    tours: dict[str, TourRate] = {}
    for n, r in _rows(ws):
        source_id = str(r["Tour ID"]).strip()
        tour_id = normalise_tour_id(source_id)
        if tour_id != source_id:
            issues.append(DataIssue(
                code="inconsistent_tour_id", location=f"Tours!row {n}",
                detail=f"Tour ID {source_id!r}; the content uses {tour_id!r}.",
                handling=f"Normalised to {tour_id}."))
        hotels_cell = str(r["Hotels by night (in order)"] or "").strip()
        hotel_ids = tuple(h.strip() for h in hotels_cell.split(",")
                          if h.strip() and h.strip() not in {"–", "-"})
        notes = (str(r["Notes"]).strip() or None) if r.get("Notes") else None
        if notes:
            issues.append(DataIssue(
                code="tour_note", location=f"Tours!row {n}",
                detail=f"{tour_id}: note {notes!r}.",
                handling="Shown to staff; the tour's content status decides whether it is offered."))
        kind = TourKind.DAY if str(r["Type"]).strip().lower().startswith("day") else TourKind.MULTI_DAY
        tours[tour_id] = TourRate(
            tour_id=tour_id, source_id=source_id, name=str(r["Tour"]).strip(), kind=kind,
            days=int(r["Days"]), nights=int(r["Nights"]),
            guide_lkr_per_day=Decimal(str(_col(r, "Guide"))),
            entrance_adult_lkr=Decimal(str(_col(r, "Entrance adult"))),
            entrance_child_lkr=Decimal(str(_col(r, "Entrance child"))),
            meals_lkr_per_adult_per_day=Decimal(str(_col(r, "Meals"))),
            hotel_ids_by_night=hotel_ids, notes=notes, row=n)
    return tours


def _load_hotels(ws, issues: list[DataIssue]) -> list[HotelRate]:
    hotels: list[HotelRate] = []
    for n, r in _rows(ws, header_row=HOTELS_HEADER_ROW):
        hid = str(r["Hotel ID"]).strip()
        notes = (str(r["Notes"]).strip() or None) if r.get("Notes") else None
        currency: Literal["LKR", "USD"] = "USD" if notes and "USD" in notes.upper() else "LKR"
        if currency == "USD":
            issues.append(DataIssue(
                code="usd_rate", location=f"Hotels!row {n}",
                detail=f"{hid} {r['Season']} rates are in USD ({notes}); the sheet header says LKR.",
                handling="Kept in USD and added to the cost without FX conversion."))

        dates = {}
        for field, col in (("valid_from", "Valid from"), ("valid_to", "Valid to")):
            dates[field], was_text = parse_date(r[col])
            if was_text:
                issues.append(DataIssue(
                    code="text_date", location=f"Hotels!row {n}",
                    detail=f"{hid} {col} stored as text {r[col]!r}.",
                    handling=f"Parsed day-first as {dates[field].isoformat()}."))

        money = {}
        for field, col in (("double_room", "Double room"), ("single_room", "Single room"),
                           ("extra_bed_child", "Extra bed")):
            raw = _col(r, col)
            money[field], was_text = parse_money(raw)
            if was_text:
                issues.append(DataIssue(
                    code="text_price", location=f"Hotels!row {n}",
                    detail=f"{hid} {col} stored as text {raw!r}.",
                    handling=f"Parsed as {money[field]}."))
            if money[field] is None:
                issues.append(DataIssue(
                    code="missing_rate", location=f"Hotels!row {n}",
                    detail=f"{hid} {r['Hotel']} has no {col.lower()} rate ({r['Season']}).",
                    handling="Never treated as 0: a booking that needs it goes to a specialist."))

        hotels.append(HotelRate(
            hotel_id=hid, hotel_name=str(r["Hotel"]).strip(), season=str(r["Season"]).strip(),
            currency=currency, notes=notes, row=n, **dates, **money))
    return hotels


def _load_vehicles(ws) -> list[Vehicle]:
    return [Vehicle(name=str(r["Vehicle"]).strip(), min_travellers=int(r["Min travellers"]),
                    max_travellers=int(r["Max travellers"]),
                    lkr_per_day=Decimal(str(_col(r, "LKR per day")))) for _, r in _rows(ws)]


# ---------------------------------------------------------------- consistency checks

def _check_overlaps(hotels: list[HotelRate]) -> list[DataIssue]:
    issues = []
    by_hotel: dict[str, list[HotelRate]] = {}
    for h in hotels:
        by_hotel.setdefault(h.hotel_id, []).append(h)
    for hid, rows in by_hotel.items():
        for i, a in enumerate(rows):
            for b in rows[i + 1:]:
                if a.valid_from <= b.valid_to and b.valid_from <= a.valid_to:
                    start, end = max(a.valid_from, b.valid_from), min(a.valid_to, b.valid_to)
                    issues.append(DataIssue(
                        code="rate_conflict", location=f"Hotels!rows {a.row} & {b.row}",
                        detail=(f"{hid} {a.hotel_name} has two rows covering {start}..{end} "
                                f"({a.double_room} vs {b.double_room} double; note: {b.notes or a.notes})."),
                        handling="Nights in that range are not priced; a specialist confirms the rate."))
    return issues


def _check_expired(hotels: list[HotelRate], seasons: list[Season]) -> list[DataIssue]:
    window_start = min(s.valid_from for s in seasons)
    issues = []
    for hid in sorted({h.hotel_id for h in hotels}):
        rows = [h for h in hotels if h.hotel_id == hid]
        last = max(h.valid_to for h in rows)
        if last < window_start:
            issues.append(DataIssue(
                code="expired_rate", location=f"Hotels!rows {rows[0].row}-{rows[-1].row}",
                detail=f"{hid} {rows[0].hotel_name}: all rates end by {last}, before the "
                       f"{window_start} start of the quoting year.",
                handling="No covering rate: tours using it go to a specialist."))
    return issues


def _check_tour_hotels(tours: dict[str, TourRate], hotels: list[HotelRate]) -> list[DataIssue]:
    known = {h.hotel_id for h in hotels}
    issues = []
    for t in tours.values():
        if len(t.hotel_ids_by_night) != t.nights:
            issues.append(DataIssue(
                code="hotel_night_mismatch", location=f"Tours!row {t.row}",
                detail=f"{t.tour_id} has {t.nights} nights but {len(t.hotel_ids_by_night)} hotel entries.",
                handling="Not priced; a specialist confirms."))
        for hid in sorted(set(t.hotel_ids_by_night) - known):
            issues.append(DataIssue(
                code="unknown_hotel", location=f"Tours!row {t.row}",
                detail=f"{t.tour_id} uses hotel {hid}, which has no rates.",
                handling="Not priced; a specialist confirms."))
    return issues


def load_rate_book(dataset_dir: Path) -> RateBook:
    wb = load_workbook(dataset_dir / WORKBOOK_PATH, read_only=True, data_only=True)
    try:
        issues: list[DataIssue] = []
        settings = _load_settings(wb["Settings"])
        seasons = _load_seasons(wb["Seasons"])
        tours = _load_tours(wb["Tours"], issues)
        hotels = _load_hotels(wb["Hotels"], issues)
        vehicles = _load_vehicles(wb["Transport"])
    finally:
        wb.close()   # read-only mode keeps the file open until closed; never saved
    issues += _check_overlaps(hotels) + _check_expired(hotels, seasons) + _check_tour_hotels(tours, hotels)
    return RateBook(settings=settings, seasons=seasons, tours=tours, hotels=hotels,
                    vehicles=vehicles, issues=issues)
