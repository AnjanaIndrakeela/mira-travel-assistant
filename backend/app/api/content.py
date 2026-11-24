"""R8 content approval (steps 17.7-17.11).

POST /staff/content                 staff: a command -> the content agent drafts a tour -> saved as DRAFT
GET  /staff/content                 staff: drafts, published and rejected items
GET  /staff/content/{id}            staff: preview (Markdown, itinerary, pictures, sources)
POST /staff/content/{id}/publish    APPROVER only (require_role, in code): publish + re-index the RAG
POST /staff/content/{id}/reject     APPROVER only: reject with a note
GET  /media/{tag}/{file}            our own media library (illustrations), for the preview

A draft is never retrieved, matched or priced: it isn't in the content library until published.
A published tour has no rate row, so asking its price gives a specialist flag (no_rate_row).
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import get_settings
from app.core.security import require_role
from app.db.models import ContentItem, Media, User
from app.graph.content_workflow import (ContentFlow, go_live, media_rows, next_tour_id, save_draft,
                                        to_content_doc)

logger = logging.getLogger("mira.content")
router = APIRouter()


class CommandIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    command: str = Field(min_length=5, max_length=500)


class RejectIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    note: str = Field(default="", max_length=500)


class ItemSummary(BaseModel):
    id: uuid.UUID
    status: str
    title: str
    doc_id: str | None
    days: int | None
    places: list[str]
    created_by: str
    approved_by: str | None
    created_at: datetime
    published_at: datetime | None


class ItemOut(ItemSummary):
    body: str
    overview: str
    itinerary: list[dict[str, Any]]
    media: list[dict[str, str]]
    sources: list[str]
    command: str
    review_note: str | None
    indexed: bool | None = None


def _emails(db: Session, *ids) -> dict:
    ids = {i for i in ids if i}
    return {u.id: u.email for u in db.scalars(select(User).where(User.id.in_(ids)))} if ids else {}


def _summary(item: ContentItem, emails: dict) -> dict:
    return {"id": item.id, "status": item.status, "title": item.title, "doc_id": item.data.get("doc_id"),
            "days": item.data.get("days"), "places": item.data.get("places", []),
            "created_by": emails.get(item.created_by, "?"), "approved_by": emails.get(item.approved_by),
            "created_at": item.created_at, "published_at": item.published_at}


def _out(db: Session, item: ContentItem, **extra) -> ItemOut:
    emails = _emails(db, item.created_by, item.approved_by)
    media = [{"id": str(m.id), "url": f"/api/v1/media/{m.path}", "alt": m.alt}
             for m in db.scalars(select(Media).where(Media.id.in_([uuid.UUID(i) for i in item.media_ids])))] \
        if item.media_ids else []
    return ItemOut(**_summary(item, emails), body=item.body, overview=item.data.get("overview", ""),
                   itinerary=item.data.get("itinerary", []), media=media, sources=item.data.get("sources", []),
                   command=item.data.get("command", ""), review_note=item.review_note, **extra)


def _item(db: Session, item_id: uuid.UUID) -> ContentItem:
    item = db.get(ContentItem, item_id)
    if item is None:
        raise HTTPException(404, "We couldn't find that content item.")
    return item


@router.post("/staff/content", response_model=ItemOut, status_code=201, tags=["content"])
def create(req: CommandIn, db: Session = Depends(get_db), user=Depends(require_role("staff"))) -> ItemOut:
    from app.data_loader import get_dataset
    flow = ContentFlow(get_dataset().content, media_rows(db))
    result = flow.run(req.command)
    if result.get("errors"):
        raise HTTPException(422, "The draft didn't pass our checks: " + " ".join(result["errors"]))
    item = save_draft(db, result, created_by=user.id, command=req.command)
    db.commit()
    logger.info("content draft %s created by %s", item.id, user.role)
    return _out(db, item)


@router.get("/staff/content", response_model=list[ItemSummary], tags=["content"])
def list_items(db: Session = Depends(get_db), user=Depends(require_role("staff"))) -> list[dict]:
    items = list(db.scalars(select(ContentItem).order_by(ContentItem.created_at.desc())))
    emails = _emails(db, *(i.created_by for i in items), *(i.approved_by for i in items))
    return [_summary(i, emails) for i in items]


@router.get("/staff/content/{item_id}", response_model=ItemOut, tags=["content"])
def read_item(item_id: uuid.UUID, db: Session = Depends(get_db), user=Depends(require_role("staff"))) -> ItemOut:
    return _out(db, _item(db, item_id))


@router.post("/staff/content/{item_id}/publish", response_model=ItemOut, tags=["content"])
def publish(item_id: uuid.UUID, db: Session = Depends(get_db), user=Depends(require_role("approver"))) -> ItemOut:
    from app.data_loader import get_dataset
    item = _item(db, item_id)
    if item.status != "draft":
        raise HTTPException(409, f"Only a draft can be published; this one is {item.status}.")
    item.data = {**item.data, "doc_id": next_tour_id(get_dataset().content, db)}
    item.status, item.approved_by = "published", user.id
    item.published_at = datetime.now(timezone.utc)
    db.commit()
    indexed = True
    try:
        go_live([to_content_doc(item)])                  # library + catalog + RAG index (17.10)
    except Exception:  # noqa: BLE001  (logged in go_live; the next restart indexes it)
        indexed = False
    logger.info("content %s published as %s", item.id, item.data["doc_id"])
    return _out(db, item, indexed=indexed)


@router.post("/staff/content/{item_id}/reject", response_model=ItemOut, tags=["content"])
def reject(item_id: uuid.UUID, req: RejectIn, db: Session = Depends(get_db),
           user=Depends(require_role("approver"))) -> ItemOut:
    item = _item(db, item_id)
    if item.status != "draft":
        raise HTTPException(409, f"Only a draft can be rejected; this one is {item.status}.")
    item.status, item.review_note = "rejected", req.note or None
    db.commit()
    return _out(db, item)


@router.get("/media/{tag}/{name}", include_in_schema=False)
def media_file(tag: str, name: str, db: Session = Depends(get_db)) -> FileResponse:
    row = db.scalar(select(Media).where(Media.path == f"{tag}/{name}"))      # only registered files
    if row is None:
        raise HTTPException(404, "No such picture.")
    path = (get_settings().mira_media_dir / row.path).resolve()
    if not path.is_relative_to(get_settings().mira_media_dir.resolve()) or not path.is_file():
        raise HTTPException(404, "No such picture.")
    return FileResponse(path, headers={"Cache-Control": "public, max-age=86400"})      # files never change in place
