"""The fixed catalog of UI components Mira may show (plan §7.4, step 11.2).

The agent can only CHOOSE from these nine types; it can never invent UI. Every payload is a
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
# only files our own media route serves (registered in the media table)
MediaSrc = Annotated[str, Field(pattern=r"^/api/v1/media/[a-z0-9-]+/[a-z0-9][a-z0-9.-]*\.(?:jpg|jpeg|png|svg|webp)$")]
CommonsPage = Annotated[str, Field(pattern=r"^https://commons\.wikimedia\.org/wiki/File:[^\s<>\"']+$", max_length=300)]


class _Component(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SourceRef(_Component):
    doc_id: DocId
    title: T120


class Image(_Component):
    """A picture from our media library. Open-licence photos carry the credit the licence asks for."""

    src: MediaSrc
    alt: T200
    credit: T120 | None = None
    licence: T40 | None = None
    source: CommonsPage | None = None


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
    hotels: list[T160] = Field(default_factory=list, max_length=10,
                               description="Where the tour stays, from its published page")
    accent: Accent
    bookable: bool = Field(description="Mira can price it instantly")
    source: SourceRef
    images: list[Image] = Field(default_factory=list, max_length=3)


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
    image: Image | None = None


class PriceBreakdown(_Component):
    """Quote ID only: the browser fetches the verified public quote from /quotes/{id}."""

    type: Literal["price_breakdown"]
    quote_id: uuid.UUID


class BookingForm(_Component):
    type: Literal["booking_form"]
    quote_id: uuid.UUID
    fields: list[Literal["name", "email", "phone", "card"]] = Field(
        default_factory=lambda: ["name", "email", "phone", "card"], min_length=1,
        description="card = the full mock card form: holder, type, number, expiry, security code")


SpecialistReason = Literal["no_price", "custom_request", "custom_plan", "unanswered_question", "handoff",
                           "booking_failed"]


class SpecialistNotice(_Component):
    """No price or no answer: a specialist takes over. The message is code-written, never the LLM's.
    custom_plan: offered under suggested tours, with `summary` (what the traveller asked for,
    written by code from the trip details) pre-filled in the enquiry form."""

    type: Literal["specialist_notice"]
    reason: SpecialistReason
    message: T400
    enquiry_id: uuid.UUID | None = None
    summary: T400 | None = None


class SourceItem(_Component):
    n: int = Field(ge=1, le=20)
    doc_id: DocId
    title: T120
    section: T160


class SourceList(_Component):
    type: Literal["source_list"]
    items: list[SourceItem] = Field(min_length=1, max_length=8)


class PhotoGallery(_Component):
    """Pictures of the places a planned or requested trip visits (chosen by code, never the LLM)."""

    type: Literal["photo_gallery"]
    title: T120
    images: list[Image] = Field(min_length=1, max_length=6)


class WelcomeBack(_Component):
    """R2: greeting for a returning visitor; the last quote is re-priced, shown by quote_id.
    No tour_title: they chatted before but never got a price."""

    type: Literal["welcome_back"]
    tour_title: T120 | None = None
    quote_id: uuid.UUID | None = None


class PlanDay(_Component):
    day: int = Field(ge=1, le=14)
    title: T160
    description: T1200
    stay: T160 | None = Field(default=None, description="Tonight's hotel, as our pages name it")


class TripPlan(_Component):
    """A custom plan the planner agent wrote for this traveller from our published content (RAG).
    A draft: no price; the team confirms and prices it from the saved enquiry."""

    type: Literal["trip_plan"]
    title: T120
    overview: T1200
    days: list[PlanDay] = Field(min_length=1, max_length=14)
    sources: list[SourceRef] = Field(default_factory=list, max_length=8)
    images: list[Image] = Field(default_factory=list, max_length=3)


UIComponent = Annotated[
    Union[TravellerPicker, TourCard, ItineraryDay, PriceBreakdown, BookingForm, SpecialistNotice,
          SourceList, WelcomeBack, PhotoGallery, TripPlan],
    Field(discriminator="type"),
]
COMPONENT_TYPES = ("traveller_picker", "tour_card", "itinerary_day", "price_breakdown", "booking_form",
                   "specialist_notice", "source_list", "welcome_back", "photo_gallery", "trip_plan")
ADAPTER: TypeAdapter[UIComponent] = TypeAdapter(UIComponent)


def json_schema() -> dict:
    """The catalog's JSON Schema (exported to the frontend)."""
    return ADAPTER.json_schema(mode="serialization")
