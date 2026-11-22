"""Load the Markdown content (tours, destinations, policies) into structured, cleaned docs.

Read-only. Problems are fixed in memory and logged as DataIssues:
- HTML comments are removed (one hides instructions aimed at the assistant).
- Guest testimonials are marked as opinion, never as facts.
- Old pages are marked stale; offers for seasons that have ended are marked expired.
"""

from __future__ import annotations

import re
from datetime import date
from enum import Enum
from pathlib import Path

import frontmatter
from pydantic import BaseModel, Field

from app.data_loader.issues import DataIssue

CONTENT_DIR = Path("content")
STALE_BEFORE = date(2025, 1, 1)   # pages last updated before this are treated as out of date

_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
_DAY = re.compile(r"^Day\s+(\d+)\s*:\s*(.+)$", re.IGNORECASE)
_FIELD = re.compile(r"^\s*[-*]\s+\*\*(.+?):\*\*\s*(.*)$")
_SEASON = re.compile(r"\b20(\d\d)/(\d\d)\b")   # e.g. "Winter 2023/24"

_ITINERARY_FIELDS = {
    "meals": "meals",
    "accommodation": "accommodation",
    "entrance tickets included": "entrance_tickets",
    "other inclusions": "other_inclusions",
}


class Trust(str, Enum):
    FACT = "fact"          # company content: may be used to answer questions
    OPINION = "opinion"    # guest reviews: never used as facts, prices or promises


class Section(BaseModel):
    heading: str
    level: int
    text: str


class ItineraryDay(BaseModel):
    day: int
    title: str
    description: str
    meals: str | None = None
    accommodation: str | None = None
    entrance_tickets: str | None = None
    other_inclusions: str | None = None


class ContentDoc(BaseModel):
    id: str
    type: str                       # tour | destination | policy | faq | page
    title: str
    status: str                     # published | draft
    last_updated: date | None
    path: str                       # relative to the dataset, POSIX style
    meta: dict = Field(default_factory=dict)   # remaining front matter (category, duration, ...)
    body: str                       # cleaned Markdown, without front matter
    sections: list[Section]
    itinerary: list[ItineraryDay]
    trust: Trust
    stale: bool                     # older page: newer policies override it
    expired_offer: bool             # names a season that has already ended

    @property
    def is_published(self) -> bool:
        return self.status == "published"


class ContentLibrary(BaseModel):
    docs: list[ContentDoc]
    issues: list[DataIssue] = Field(default_factory=list)

    def published(self) -> list[ContentDoc]:
        """Everything a traveller may see. Drafts are never included."""
        return [d for d in self.docs if d.is_published]

    def get(self, doc_id: str) -> ContentDoc | None:
        return next((d for d in self.docs if d.id == doc_id), None)

    def get_published(self, doc_id: str) -> ContentDoc | None:
        doc = self.get(doc_id)
        return doc if doc and doc.is_published else None

    def by_type(self, doc_type: str, published_only: bool = True) -> list[ContentDoc]:
        docs = self.published() if published_only else self.docs
        return [d for d in docs if d.type == doc_type]


def _to_date(value) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _split_sections(body: str) -> list[Section]:
    """Split on level-2+ headings. Text before the first one is the 'Overview'.

    The level-1 heading is the page title, so it is dropped from the text.
    """
    body = re.sub(r"^#\s+.+$", "", body, count=1, flags=re.MULTILINE)
    sections: list[Section] = []
    heading, level, start = "Overview", 1, 0
    for m in _HEADING.finditer(body):
        if len(m.group(1)) < 2:
            continue
        text = body[start:m.start()].strip()
        if text:
            sections.append(Section(heading=heading, level=level, text=text))
        heading, level, start = m.group(2), len(m.group(1)), m.end()
    text = body[start:].strip()
    if text:
        sections.append(Section(heading=heading, level=level, text=text))
    return sections


def _parse_itinerary(sections: list[Section]) -> list[ItineraryDay]:
    days: list[ItineraryDay] = []
    for s in sections:
        m = _DAY.match(s.heading)
        if not m:
            continue
        fields: dict[str, str] = {}
        description: list[str] = []
        for line in s.text.splitlines():
            f = _FIELD.match(line)
            if f and f.group(1).strip().lower() in _ITINERARY_FIELDS:
                fields[_ITINERARY_FIELDS[f.group(1).strip().lower()]] = f.group(2).strip()
            elif line.strip():
                description.append(line.strip())
        days.append(ItineraryDay(day=int(m.group(1)), title=m.group(2).strip(),
                                 description=" ".join(description), **fields))
    return days


def has_expired_season(text: str, today: date) -> bool:
    """True if the text names a season like '2023/24' whose second year is before today's."""
    for m in _SEASON.finditer(text):
        end_year = 2000 + int(m.group(2))
        if int(m.group(2)) == (int(m.group(1)) + 1) % 100 and end_year < today.year:
            return True
    return False


def _load_doc(path: Path, dataset_dir: Path, today: date, issues: list[DataIssue]) -> ContentDoc:
    rel = path.relative_to(dataset_dir).as_posix()
    post = frontmatter.load(path)
    meta = dict(post.metadata)

    body = post.content
    if _COMMENT.search(body):
        body = _COMMENT.sub("", body)
        issues.append(DataIssue(
            code="hidden_comment_removed", location=rel,
            detail="An HTML comment with instructions aimed at the assistant was found in the page.",
            handling="HTML comments are removed when the content is loaded; they never reach the model."))

    doc_id = str(meta.pop("id"))
    doc_type = str(meta.pop("type"))
    title = str(meta.pop("title"))
    status = str(meta.pop("status"))
    last_updated = _to_date(meta.pop("last_updated", None))

    trust = Trust.OPINION if path.stem == "testimonials" else Trust.FACT
    if trust is Trust.OPINION:
        issues.append(DataIssue(
            code="opinion_content", location=rel,
            detail="Guest testimonials: claims about discounts, upgrades and wildlife are opinions, "
                   "and one line addresses the assistant directly.",
            handling="Marked as opinion: never used for facts, prices or promises."))

    stale = last_updated is not None and last_updated < STALE_BEFORE
    if stale and status == "published":
        issues.append(DataIssue(
            code="stale_page", location=rel,
            detail=f"{doc_id} was last updated {last_updated}.",
            handling="Ranked below current pages; current policies override it."))

    expired_offer = has_expired_season(f"{title}\n{body}", today)
    if expired_offer:
        issues.append(DataIssue(
            code="expired_offer", location=rel,
            detail=f"{doc_id} {title!r} is an offer for a season that has ended.",
            handling="Never offered or priced; requests go to a specialist."))

    if status != "published":
        issues.append(DataIssue(
            code="draft_content", location=rel,
            detail=f"{doc_id} {title!r} has status {status!r}.",
            handling="Never shown, retrieved or priced for travellers."))

    sections = _split_sections(body)
    return ContentDoc(
        id=doc_id, type=doc_type, title=title, status=status, last_updated=last_updated,
        path=rel, meta=meta, body=body.strip(), sections=sections,
        itinerary=_parse_itinerary(sections), trust=trust, stale=stale,
        expired_offer=expired_offer)


def load_content(dataset_dir: Path, today: date) -> ContentLibrary:
    issues: list[DataIssue] = []
    paths = sorted((dataset_dir / CONTENT_DIR).rglob("*.md"))
    docs = [_load_doc(p, dataset_dir, today, issues) for p in paths]

    teasers = sorted(d.id for d in docs if "teaser_price" in d.meta)
    if teasers:
        issues.append(DataIssue(
            code="teaser_price", location="content/tours/* (front matter)",
            detail=f"{len(teasers)} tour pages carry a 'teaser_price' text: {', '.join(teasers)}.",
            handling="Never shown; every price comes from the pricing engine and the rate workbook."))
    return ContentLibrary(docs=docs, issues=issues)
