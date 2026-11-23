"""Published content -> small, self-contained, citable chunks (plan §16 step 3).

- Only published docs (no drafts such as T15; hidden HTML comments were removed on load).
- One chunk per section; itinerary days get stable "#day-N" IDs (e.g. "T09#day-3").
- One "facts" chunk per tour from its front matter (duration, start, places, hotels),
  never its teaser price.
- Every chunk starts with "{title} — {section}" so it makes sense on its own.
- Money amounts are masked: prices come only from the pricing engine, never from text.
- Testimonials keep trust=opinion; stale and expired-offer flags are kept for the retriever.
"""

from __future__ import annotations

import re

from pydantic import BaseModel

from app.data_loader.content_loader import ContentDoc, ContentLibrary, Trust

MAX_CHARS = 1200

TOUR_PRICE_MASK = "[price: ask Mira for a quote]"
OTHER_AMOUNT_MASK = "[amount: a travel specialist can confirm]"
# USD 120 / US$ 1,350 / $35 / LKR 28,000 / Rs. 5000 / Rs 5,000 / 4,500 rupees
MONEY = re.compile(
    r"(?:\b(?:USD|US\$|LKR|Rs\.?|SLR)\s?\$?\s?\d[\d,]*(?:\.\d+)?"
    r"|\$\s?\d[\d,]*(?:\.\d+)?"
    r"|\b\d[\d,]*(?:\.\d+)?\s?(?:USD|LKR|rupees|dollars)\b)",
    re.IGNORECASE,
)


class Chunk(BaseModel, frozen=True):
    id: str                  # stable: "T09#day-3", "P02#day-and-city-tours", "T04#facts"
    doc_id: str
    doc_type: str            # tour | destination | policy | faq | page
    title: str
    section: str
    text: str                # what is embedded, indexed and shown to the LLM
    path: str                # dataset-relative path, for the citation
    trust: Trust
    stale: bool
    expired_offer: bool
    tour_id: str | None = None


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "section"


def mask_money(text: str, doc_type: str) -> str:
    mask = TOUR_PRICE_MASK if doc_type in ("tour", "destination") else OTHER_AMOUNT_MASK
    return MONEY.sub(mask, text)


def _split(text: str) -> list[str]:
    """Split long text on paragraph breaks into pieces of at most ~MAX_CHARS."""
    if len(text) <= MAX_CHARS:
        return [text]
    parts, current = [], ""
    for para in re.split(r"\n\s*\n", text):
        if current and len(current) + len(para) + 2 > MAX_CHARS:
            parts.append(current)
            current = para
        else:
            current = f"{current}\n\n{para}" if current else para
    return parts + ([current] if current else [])


def _facts_text(doc: ContentDoc) -> str | None:
    m = doc.meta
    lines = []
    for key, label in (("category", "Type"), ("duration", "Duration"), ("start", "Starts from")):
        if m.get(key):
            lines.append(f"{label}: {m[key]}")
    if m.get("destinations"):
        places = ", ".join(str(p).replace("-", " ").title() for p in m["destinations"])
        lines.append(f"Places: {places}")
    if m.get("hotels"):
        lines.append(f"Hotels: {', '.join(map(str, m['hotels']))}")
    return "\n".join(lines) or None          # teaser_price deliberately left out


_DAY = re.compile(r"^Day\s+(\d+)\b", re.IGNORECASE)


def chunks_for_doc(doc: ContentDoc) -> list[Chunk]:
    base = dict(doc_id=doc.id, doc_type=doc.type, title=doc.title, path=doc.path, trust=doc.trust,
                stale=doc.stale, expired_offer=doc.expired_offer,
                tour_id=doc.id if doc.type == "tour" else None)
    out: list[Chunk] = []
    seen: set[str] = set()

    def add(slug: str, section: str, body: str) -> None:
        body = mask_money(body.strip(), doc.type)
        if not body:
            return
        pieces = _split(body)
        for i, piece in enumerate(pieces, 1):
            cid = f"{doc.id}#{slug}" + (f"-{i}" if len(pieces) > 1 else "")
            n = 2
            while cid in seen:                      # duplicate headings stay unique and stable
                cid = f"{doc.id}#{slug}-{n}"
                n += 1
            seen.add(cid)
            out.append(Chunk(id=cid, section=section, text=f"{doc.title} — {section}\n\n{piece}", **base))

    if doc.type == "tour" and (facts := _facts_text(doc)):
        add("facts", "Facts", facts)
    for section in doc.sections:
        m = _DAY.match(section.heading)
        slug = f"day-{m.group(1)}" if m and doc.type == "tour" else slugify(section.heading)
        add(slug, section.heading, section.text)
    return out


def build_chunks(library: ContentLibrary) -> list[Chunk]:
    return [c for doc in sorted(library.published(), key=lambda d: d.id) for c in chunks_for_doc(doc)]
