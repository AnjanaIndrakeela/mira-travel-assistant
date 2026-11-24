"""Request and response shapes for the public API (step 9.1).

Typed like the graph state: Swagger shows them, and a bad request is rejected before any
code runs. No response here has a cost, margin or GP field.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.guards.input_guard import MAX_CHARS


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ChatRequest(_In):
    conversation_id: uuid.UUID | None = Field(
        default=None, description="Omit to start a new conversation; send it back to continue one")
    visitor_id: uuid.UUID | None = Field(
        default=None, description="Anonymous ID kept by the browser; omit on the first visit")
    message: str = Field(min_length=1, max_length=MAX_CHARS * 2,
                         description="The traveller's message (longer than 2,000 characters is cut)")


class Source(BaseModel):
    n: int
    doc_id: str
    title: str
    section: str


class ChatResponse(BaseModel):
    conversation_id: uuid.UUID
    visitor_id: uuid.UUID
    message: str
    ui: list[dict[str, Any]] = Field(description="UI components from the fixed catalog, in order")
    sources: list[Source] = []
    quote_id: uuid.UUID | None = None
    enquiry_id: uuid.UUID | None = None


class ChatMessage(BaseModel):
    role: Literal["traveller", "mira"]
    text: str
    ui: list[dict[str, Any]] = []         # Mira's cards for that reply (already validated)


class ConversationOut(BaseModel):
    conversation_id: uuid.UUID
    visitor_id: uuid.UUID
    messages: list[ChatMessage]


class Contact(_In):
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    phone: str | None = Field(default=None, max_length=40)


class EnquiryRequest(_In):
    kind: Literal["custom", "quote", "no_price"] = "custom"
    conversation_id: uuid.UUID | None = None
    quote_id: uuid.UUID | None = None
    notes: str | None = Field(default=None, max_length=2000, description="What the traveller would like")
    contact: Contact | None = None


class EnquiryOut(BaseModel):
    enquiry_id: uuid.UUID
    message: str


class TourDay(BaseModel):
    day: int
    title: str
    description: str
    meals: str | None = None
    accommodation: str | None = None


class TourOut(BaseModel):
    tour_id: str
    title: str
    category: str
    duration: str
    start: str | None = None
    destinations: list[str]
    hotels: list[str] = []
    itinerary: list[TourDay]
    body: str = Field(description="The tour page in Markdown; prices removed (ask Mira for a quote)")
    bookable: bool = Field(description="True if Mira can price it instantly")
    last_updated: date | None = None


class Card(_In):
    """MOCK payment only: checked like a real card, never stored or logged (only the card type and
    last four digits are kept). 4242 4242 4242 4242 succeeds, 4000 0000 0000 0002 fails."""

    holder: str = Field(min_length=2, max_length=80, description="Name on the card")
    brand: Literal["visa", "mastercard", "amex"]
    number: str = Field(min_length=12, max_length=23, pattern=r"^[\d -]+$")
    exp_month: int = Field(ge=1, le=12)
    exp_year: int = Field(ge=0, le=2100, description="YY or YYYY")
    cvc: str = Field(min_length=3, max_length=4, pattern=r"^\d+$")


class BookingRequest(_In):
    quote_id: uuid.UUID
    contact: Contact
    card: Card


class BookingOut(BaseModel):
    status: Literal["confirmed", "payment_failed", "price_changed"]
    message: str
    booking_id: uuid.UUID | None = None
    payment_reference: str | None = None
    amount_charged_usd: int | None = None
    next_steps: list[Literal["retry", "payment_link", "enquiry_saved", "new_quote"]] = []
    enquiry_id: uuid.UUID | None = None
    field: Literal["holder", "brand", "number", "expiry", "cvc"] | None = None   # the card detail to fix
    card: str | None = None                       # "Visa ending 4242" on a confirmed booking


class ErrorOut(BaseModel):
    error: str
    message: str
