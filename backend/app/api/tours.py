"""GET /tours/{id} (step 9.7): published tours only (a draft such as T15 is a 404).

Prices in the page text are masked: the only prices travellers see come from the engine.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.api.schemas import TourDay, TourOut
from app.data_loader import get_dataset
from app.data_loader.rate_loader import normalise_tour_id
from app.rag.chunker import mask_money

router = APIRouter(tags=["tours"])


@router.get("/tours/{tour_id}", response_model=TourOut)
def read_tour(tour_id: str, request: Request) -> TourOut:
    ds = getattr(request.app.state, "dataset", None) or get_dataset()
    try:
        tid = normalise_tour_id(tour_id.strip().upper())
    except ValueError:
        tid = tour_id
    doc = ds.content.get_published(tid)
    if doc is None or doc.type != "tour":
        raise HTTPException(404, "We don't have that tour in our current programme.")
    meta = doc.meta
    return TourOut(
        tour_id=doc.id, title=doc.title, category=str(meta.get("category", "")),
        duration=str(meta.get("duration", "")), start=meta.get("start"),
        destinations=list(meta.get("destinations", [])), hotels=list(meta.get("hotels", [])),
        itinerary=[TourDay(day=d.day, title=d.title, description=mask_money(d.description, "tour"),
                           meals=d.meals, accommodation=d.accommodation) for d in doc.itinerary],
        body=mask_money(doc.body, "tour"),
        bookable=doc.id in ds.rates.tours and not doc.expired_offer,
        last_updated=doc.last_updated)
