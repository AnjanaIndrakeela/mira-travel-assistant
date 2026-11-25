"""The hotel stays a priced tour uses (for booking them): the Tours tab's hotel for each night,
consecutive nights in one hotel as one stay, rooms by rule 4, exactly as priced. No costs."""

from __future__ import annotations

from datetime import date, timedelta

from app.data_loader.rate_loader import RateBook
from app.pricing.calculator import Rooms
from app.pricing.party import Party, build_party


def hotel_stays(tour_id: str, start: date, adults: int, child_ages, rates: RateBook) -> list[dict]:
    """[{hotel_id, hotel, check_in, check_out, nights, rooms}] in order; [] for a day tour."""
    tour = rates.tours.get(tour_id)
    party = build_party(adults, child_ages)
    if tour is None or not tour.hotel_ids_by_night or not isinstance(party, Party):
        return []
    rooms = Rooms.for_party(party).describe()
    out: list[dict] = []
    for i, hotel_id in enumerate(tour.hotel_ids_by_night):
        night = start + timedelta(days=i)
        if out and out[-1]["hotel_id"] == hotel_id and out[-1]["check_out"] == night:
            out[-1]["check_out"] = night + timedelta(days=1)
            out[-1]["nights"] += 1
        else:
            out.append({"hotel_id": hotel_id, "hotel": rates.hotel_name(hotel_id), "check_in": night,
                        "check_out": night + timedelta(days=1), "nights": 1, "rooms": rooms})
    return out
