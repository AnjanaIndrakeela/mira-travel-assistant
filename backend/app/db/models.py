"""The 8 tables Mira writes to (plan §7 / WORK_PLAN 5.2-5.8).

Allowed values are enforced twice: as Literal types in Python and as CHECK constraints in
Postgres, so a bad status can't be written even by a raw SQL insert.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal, get_args

from sqlalchemy import (DDL, CheckConstraint, Date, DateTime, ForeignKey, Integer, Numeric, String,
                        Text, event)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, utcnow

QuoteStatus = Literal["ok", "needs_specialist"]
EnquiryKind = Literal["quote", "no_price", "custom", "booking_failed"]
EnquiryStatus = Literal["new", "contacted", "pending", "confirmed", "closed"]
BookingStatus = Literal["confirmed", "payment_failed"]
UserRole = Literal["staff", "approver"]
ContentStatus = Literal["draft", "published", "rejected"]


def _check(column: str, values) -> CheckConstraint:
    allowed = ", ".join(f"'{v}'" for v in get_args(values))
    return CheckConstraint(f"{column} IN ({allowed})", name=f"{column}_allowed")


def _id() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _created() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


def _updated() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


# ------------------------------------------------------------------ 5.2 visitors (R2)

class Visitor(Base):
    __tablename__ = "visitors"

    id: Mapped[uuid.UUID] = _id()
    party: Mapped[dict | None] = mapped_column(JSONB)          # {"adults": 2, "child_ages": [7, 10]}
    traveller_type: Mapped[str | None] = mapped_column(String(40))   # family, couple, solo, group...
    interests: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    last_quote_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("quotes.id", use_alter=True, ondelete="SET NULL"))
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()

    conversations: Mapped[list[Conversation]] = relationship(back_populates="visitor")


# ------------------------------------------------------------------ 5.3 conversations

class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = _id()
    visitor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("visitors.id", ondelete="CASCADE"),
                                                  index=True, nullable=False)
    thread_id: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)   # LangGraph thread
    created_at: Mapped[datetime] = _created()

    visitor: Mapped[Visitor] = relationship(back_populates="conversations")


# ------------------------------------------------------------------ 5.4 quotes (R5, R6)

class Quote(Base):
    """One calculate_quote() result. Public and staff fields are separate columns so the
    traveller-facing read (repo.get_public_quote) never loads cost data."""

    __tablename__ = "quotes"
    __table_args__ = (
        _check("status", QuoteStatus),
        # a priced quote has a price; a refusal has reasons and no price
        CheckConstraint("(status = 'ok') = (price_usd IS NOT NULL AND cost_usd IS NOT NULL)",
                        name="price_only_when_ok"),
    )

    id: Mapped[uuid.UUID] = _id()
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"), index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    trace_id: Mapped[str | None] = mapped_column(String(64), index=True)

    # request inputs (enough to re-run calculate_quote and re-verify the price)
    tour_id: Mapped[str] = mapped_column(String(10), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    adults: Mapped[int] = mapped_column(Integer, nullable=False)
    child_ages: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)

    # public fields (NULL when status = needs_specialist)
    tour_name: Mapped[str | None] = mapped_column(String(200))
    end_date: Mapped[date | None] = mapped_column(Date)
    party_adults: Mapped[int | None] = mapped_column(Integer)
    party_children: Mapped[int | None] = mapped_column(Integer)
    party_infants: Mapped[int | None] = mapped_column(Integer)
    price_usd: Mapped[int | None] = mapped_column(Integer)
    deposit_usd: Mapped[int | None] = mapped_column(Integer)
    balance_usd: Mapped[int | None] = mapped_column(Integer)
    balance_due: Mapped[date | None] = mapped_column(Date)

    # staff-only fields
    cost_lkr: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    cost_lines: Mapped[list | None] = mapped_column(JSONB)
    fx_lkr_per_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    margin: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    gp_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    vehicle: Mapped[str | None] = mapped_column(String(40))
    rate_rows: Mapped[list | None] = mapped_column(JSONB)

    # needs_specialist: [{"code", "detail_staff", "message_traveller"}, ...]
    reasons: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    created_at: Mapped[datetime] = _created()


# ------------------------------------------------------------------ 5.5 enquiries (R7)

class Enquiry(Base):
    __tablename__ = "enquiries"
    __table_args__ = (_check("kind", EnquiryKind), _check("status", EnquiryStatus))

    id: Mapped[uuid.UUID] = _id()
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="new", nullable=False)
    quote_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("quotes.id", ondelete="SET NULL"), index=True)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"), index=True)
    trace_id: Mapped[str | None] = mapped_column(String(64), index=True)
    flags: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)    # e.g. ["missing_rate"]
    notes: Mapped[str | None] = mapped_column(Text)
    contact: Mapped[dict | None] = mapped_column(JSONB)                          # given by the traveller
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()


# ------------------------------------------------------------------ 5.6 bookings (mock)

class Booking(Base):
    __tablename__ = "bookings"
    __table_args__ = (_check("status", BookingStatus),)

    id: Mapped[uuid.UUID] = _id()
    quote_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("quotes.id", ondelete="RESTRICT"),
                                                index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    payment_ref: Mapped[str | None] = mapped_column(String(64))      # mock provider reference
    card_brand: Mapped[str | None] = mapped_column(String(20))       # never the number: card type ...
    card_last4: Mapped[str | None] = mapped_column(String(4))        # ... and last four digits only
    created_at: Mapped[datetime] = _created()


class HotelReservation(Base):
    """A hotel stay booked with a confirmed tour booking (mock): from the rate sheet's hotel for
    each night of the tour, rooms as priced. One row per stay (consecutive nights in one hotel)."""

    __tablename__ = "hotel_reservations"

    id: Mapped[uuid.UUID] = _id()
    booking_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bookings.id", ondelete="CASCADE"),
                                                  index=True, nullable=False)
    hotel_id: Mapped[str] = mapped_column(String(20), nullable=False)
    hotel_name: Mapped[str] = mapped_column(String(200), nullable=False)
    check_in: Mapped[date] = mapped_column(Date, nullable=False)
    check_out: Mapped[date] = mapped_column(Date, nullable=False)
    nights: Mapped[int] = mapped_column(Integer, nullable=False)
    rooms: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="confirmed", nullable=False)
    reference: Mapped[str] = mapped_column(String(20), nullable=False)    # mock confirmation number
    created_at: Mapped[datetime] = _created()


# ------------------------------------------------------------------ 5.7 users (staff)

class User(Base):
    __tablename__ = "users"
    __table_args__ = (_check("role", UserRole),)

    id: Mapped[uuid.UUID] = _id()
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = _created()


class StaffSession(Base):
    """A signed-in staff browser. The cookie holds a random token; only its SHA-256 is stored,
    so a database leak can't be replayed as a login. Logout deletes the row."""

    __tablename__ = "staff_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"),
                                               index=True, nullable=False)
    created_at: Mapped[datetime] = _created()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    user: Mapped[User] = relationship()


class EnquiryNote(Base):
    """A staff note on an enquiry. Append-only: there is no edit or delete endpoint, and a
    database trigger refuses UPDATE and DELETE, so the follow-up history can't be rewritten."""

    __tablename__ = "enquiry_notes"

    id: Mapped[uuid.UUID] = _id()
    enquiry_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("enquiries.id", ondelete="RESTRICT"),
                                                  index=True, nullable=False)
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = _created()

    author: Mapped[User] = relationship()


class SpecialistReply(Base):
    """A specialist's reply to the traveller (app.specialist): shown in their chat as written,
    never sent to the LLM. The mock email is recorded here (to whom, when, its text); nothing is
    delivered. Append-only, like notes: a database trigger refuses UPDATE and DELETE."""

    __tablename__ = "specialist_replies"

    id: Mapped[uuid.UUID] = _id()
    enquiry_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("enquiries.id", ondelete="RESTRICT"),
                                                  index=True, nullable=False)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"), index=True)
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    after_message: Mapped[int] = mapped_column(Integer, default=0, nullable=False)   # place in the chat
    emailed_to: Mapped[str | None] = mapped_column(String(254))          # mock email: never delivered
    email_text: Mapped[str | None] = mapped_column(Text)
    emailed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created()

    author: Mapped[User] = relationship()


event.listen(SpecialistReply.__table__, "after_create", DDL("""
CREATE OR REPLACE FUNCTION specialist_replies_append_only() RETURNS trigger AS $$
BEGIN RAISE EXCEPTION 'specialist_replies is append-only'; END $$ LANGUAGE plpgsql;
CREATE TRIGGER specialist_replies_append_only BEFORE UPDATE OR DELETE ON specialist_replies
FOR EACH ROW EXECUTE FUNCTION specialist_replies_append_only();
""").execute_if(dialect="postgresql"))


event.listen(EnquiryNote.__table__, "after_create", DDL("""
CREATE OR REPLACE FUNCTION enquiry_notes_append_only() RETURNS trigger AS $$
BEGIN RAISE EXCEPTION 'enquiry_notes is append-only'; END $$ LANGUAGE plpgsql;
CREATE TRIGGER enquiry_notes_append_only BEFORE UPDATE OR DELETE ON enquiry_notes
FOR EACH ROW EXECUTE FUNCTION enquiry_notes_append_only();
""").execute_if(dialect="postgresql"))


# ------------------------------------------------------------------ 5.8 content_items + media (R8)

class ContentItem(Base):
    """AI-drafted content. Lives only here, never in the dataset folder. A draft is never
    retrieved for travellers; only an approver can publish."""

    __tablename__ = "content_items"
    __table_args__ = (
        _check("status", ContentStatus),
        CheckConstraint("status <> 'published' OR approved_by IS NOT NULL", name="published_needs_approver"),
    )

    id: Mapped[uuid.UUID] = _id()
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    type: Mapped[str] = mapped_column(String(20), default="tour", nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)             # Markdown
    data: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)   # structured itinerary
    media_ids: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    review_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Media(Base):
    __tablename__ = "media"

    id: Mapped[uuid.UUID] = _id()
    tag: Mapped[str] = mapped_column(String(40), index=True, nullable=False)     # e.g. "ella"
    path: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)  # relative to media dir
    alt: Mapped[str] = mapped_column(String(300), nullable=False)
    # open-licence photos must show who made them and under which licence
    kind: Mapped[str] = mapped_column(String(20), default="illustration", nullable=False)   # photo | illustration
    credit: Mapped[str | None] = mapped_column(String(200))
    licence: Mapped[str | None] = mapped_column(String(40))
    licence_url: Mapped[str | None] = mapped_column(String(300))
    source: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = _created()


ALL_TABLES = ("visitors", "conversations", "quotes", "enquiries", "bookings", "users",
              "content_items", "media", "staff_sessions", "enquiry_notes")
