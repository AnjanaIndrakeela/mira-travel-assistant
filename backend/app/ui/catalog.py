"""The fixed catalog of UI components Mira may show (plan §7.4, step 11.2).

The agent can only CHOOSE from these eight types; it can never invent UI. Every payload is a
Pydantic model with extra="forbid", joined in one discriminated union on `type`, so:
- an unknown type is a validation error;
- an unknown or extra prop (for example a `price` on price_breakdown) is a validation error;
- text props refuse HTML/script and money amounts (prices come only from /quotes/{id}).

price_breakdown and booking_form carry a quote_id only: the browser fetches the verified
public quote from the API, so a price can never come from the model or from this payload.

The JSON Schema of this union is exported to the frontend (app.ui.export), where Zod checks
every payload again before it is rendered.
"""

from __future__ import annotations

import re
import uuid
from typing import Annotated, Literal, Union

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, TypeAdapter

# HTML tags, script URLs and inline handlers: never allowed in a prop
UNSAFE = re.compile(r"<\s*/?\s*[a-z!]|javascript\s*:|data\s*:\s*text/html|\bon[a-z]+\s*=", re.IGNORECASE)
# a money amount: "USD 315", "$315", "315 USD", "Rs. 5,000", "LKR 5000"
MONEY = re.compile(r"(?:\$|US\$|USD|LKR|Rs\.?|€|£)\s?\d|\d[\d,.]*\s?(?:USD|LKR|dollars?)\b", re.IGNORECASE)


def _safe(text: str) -> str:
    if UNSAFE.search(text):
        raise ValueError("markup or script is not allowed in UI text")
    if MONEY.search(text):
        raise ValueError("money amounts are not allowed in UI text (prices come from /quotes)")
    return text


def _text(n: int):
    return Annotated[str, Field(min_length=1, max_length=n), AfterValidator(_safe)]


# safe text props, by maximum length
T40, T80, T120, T160, T200, T400, T1200 = (_text(n) for n in (40, 80, 120, 160, 200, 400, 1200))


TourId = Annotated[str, Field(pattern=r"^T\d{2}$")]
DocId = Annotated[str, Field(pattern=r"^[A-Z]{1,3}\d{2,3}$")]
Accent = Literal["teal", "leaf", "sun", "sky", "coral"]


class _Component(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SourceRef(_Component):
    doc_id: DocId
    title: T120


class TravellerPicker(_Component):
    """Adults +/- and child ages; the browser sends the answer as a normal message."""

    type: Literal["traveller_picker"]
    adults: int = Field(default=2, ge=1, le=20)
    child_ages: list[Annotated[int, Field(ge=0, le=17)]] = Field(default_factory=list, max_length=10)
    ask_child_ages: bool = Field(default=False, description="A child was mentioned without an age")


class TourCard(_Component):
    type: Literal["tour_card"]
    tour_id: TourId
    title: T120
    duration: T40
    start: T120 | None = None
    highlights: list[T160] = Field(default_factory=list, max_length=4)
    why: T200 | None = None
    accent: Accent
    bookable: bool = Field(description="Mira can price it instantly")
    source: SourceRef


class ItineraryDay(_Component):
    """One day of a tour's published itinerary (T07, T08, T09 have parsed days)."""

    type: Literal["itinerary_day"]
    tour_id: TourId
    day: int = Field(ge=1, le=30)
    title: T160
    description: T1200
    meals: T80 | None = None
    stay: T160 | None = None
    source: SourceRef


class PriceBreakdown(_Component):
    """Quote ID only: the browser fetches the verified public quote from /quotes/{id}."""

    type: Literal["price_breakdown"]
    quote_id: uuid.UUID


class BookingForm(_Component):
    type: Literal["booking_form"]
    quote_id: uuid.UUID
    fields: list[Literal["name", "email", "phone", "card_number"]] = Field(
        default_factory=lambda: ["name", "email", "card_number"], min_length=1)


SpecialistReason = Literal["no_price", "custom_request", "unanswered_question", "handoff", "booking_failed"]


class SpecialistNotice(_Component):
    """No price or no answer: a specialist takes over. The message is code-written, never the LLM's."""

    type: Literal["specialist_notice"]
    reason: SpecialistReason
    message: T400
    enquiry_id: uuid.UUID | None = None


class SourceItem(_Component):
    n: int = Field(ge=1, le=20)
    doc_id: DocId
    title: T120
    section: T160


class SourceList(_Component):
    type: Literal["source_list"]
    items: list[SourceItem] = Field(min_length=1, max_length=8)


class WelcomeBack(_Component):
    """R2: greeting for a returning visitor; the last quote is re-priced, shown by quote_id."""

    type: Literal["welcome_back"]
    tour_title: T120
    quote_id: uuid.UUID | None = None


UIComponent = Annotated[
    Union[TravellerPicker, TourCard, ItineraryDay, PriceBreakdown, BookingForm, SpecialistNotice,
          SourceList, WelcomeBack],
    Field(discriminator="type"),
]
COMPONENT_TYPES = ("traveller_picker", "tour_card", "itinerary_day", "price_breakdown", "booking_form",
                   "specialist_notice", "source_list", "welcome_back")
ADAPTER: TypeAdapter[UIComponent] = TypeAdapter(UIComponent)


def json_schema() -> dict:
    """The catalog's JSON Schema (exported to the frontend)."""
    return ADAPTER.json_schema(mode="serialization")
