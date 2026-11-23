"""Data shapes for the pricing engine (plan §15 step 1).

Two kinds of "no":
- A malformed request (negative adults, missing fields, a bad date, unknown fields) is
  rejected here by validation: it is a programming or extraction error, not a traveller
  question.
- A well-formed request that cannot be priced (0 adults, 21 travellers, an age of 25 in
  child_ages, a past date, a missing rate) is *not* rejected here. It becomes a refusal with
  a reason code (reasons.py) so the traveller is handed to a specialist instead of an error.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator

from app.data_loader.rate_loader import normalise_tour_id
from app.pricing.reasons import Refusal

CostItem = Literal["guide", "vehicle", "entrance", "meals", "hotels"]   # READ ME rule 2, in order


def _no_floats(v):
    """Money is Decimal only. A float means a bug upstream, even if it would convert cleanly."""
    if isinstance(v, float):
        raise ValueError("money must be Decimal, int or a numeric string, never float")
    return v


class QuoteRequest(BaseModel):
    """What the engine needs to price one booking. Built by code, never by the LLM directly."""

    # frozen: a request can't change after it is priced; forbid: no extra inputs
    # (e.g. a "discount" field) can be smuggled in.
    model_config = ConfigDict(frozen=True, extra="forbid")

    tour_id: str = Field(min_length=1, description="Tour ID, e.g. 'T09'. 'T-13' is normalised to 'T13'.")
    start_date: date = Field(description="Tour start date; night 1 is this date.")
    adults: StrictInt = Field(ge=0, description="Adults; 0 is allowed here and refused later as no_adults.")
    child_ages: tuple[StrictInt, ...] = Field(
        default=(),
        description="Age of every non-adult traveller, infants included (e.g. (7, 10, 1)). "
                    "Ages are checked by party.py: 12+ counts as an adult, under 2 as an infant.")

    @field_validator("tour_id")
    @classmethod
    def _normalise_tour_id(cls, v: str) -> str:
        v = v.strip().upper()
        if not v:
            raise ValueError("tour_id is empty")
        try:
            return normalise_tour_id(v)       # "T-13" -> "T13", "T9" -> "T09"
        except ValueError:
            return v                           # unknown format: refused later as unknown_tour


class CostLine(BaseModel):
    """One part of the cost build-up (READ ME rule 2). Staff-only: never shown to travellers.

    Amounts are in the currency the workbook gives them in. Everything is LKR except
    hotel rows contracted in USD (H10), which go in `usd` and are never converted by FX.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    item: CostItem
    lkr: Decimal = Field(default=Decimal(0), ge=0)
    usd: Decimal = Field(default=Decimal(0), ge=0)
    detail: str = Field(min_length=1, description="How it was worked out, e.g. 'Van 26,000 × 7 days'")

    _check_money = field_validator("lkr", "usd", mode="before")(_no_floats)

    @model_validator(mode="after")
    def _usd_only_for_hotels(self) -> "CostLine":
        if self.usd and self.item != "hotels":
            raise ValueError("only hotel costs can be in USD (USD-contracted hotel rows)")
        return self


class PublicQuote(BaseModel):
    """The ONLY quote data a traveller (or the LLM) ever sees.

    It has no cost, margin or gross-profit field: those live in StaffQuote. Money is whole
    USD (the selling price is rounded up to USD 5, the deposit up to a whole USD).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    tour_id: str
    tour_name: str
    start_date: date
    end_date: date                     # last day of the tour (start + days - 1)
    adults: StrictInt = Field(ge=1)
    children: StrictInt = Field(ge=0)  # aged 2-11
    infants: StrictInt = Field(ge=0)   # under 2: free, listed so the traveller sees them counted
    price_usd: StrictInt = Field(gt=0)
    deposit_usd: StrictInt = Field(gt=0)
    balance_usd: StrictInt = Field(ge=0)
    balance_due: date | None = Field(
        default=None, description="When the balance is due (30 days before the start); None if paid in full.")
    currency: Literal["USD"] = "USD"

    @model_validator(mode="after")
    def _consistent(self) -> "PublicQuote":
        if self.end_date < self.start_date:
            raise ValueError("end_date is before start_date")
        if self.deposit_usd > self.price_usd:
            raise ValueError("deposit is more than the price")
        if self.balance_usd != self.price_usd - self.deposit_usd:
            raise ValueError("balance must equal price minus deposit")
        if (self.balance_usd == 0) != (self.balance_due is None):
            raise ValueError("balance_due is set exactly when a balance remains")
        if self.balance_due is not None and self.balance_due >= self.start_date:
            raise ValueError("balance_due must be before the start date")
        return self


GP_PLACES = Decimal("0.01")


def gross_profit_pct(price_usd: int, cost_usd: Decimal) -> Decimal:
    """Gross profit as % of the selling price, to 2 places (decision c: on the rounded price)."""
    return ((Decimal(price_usd) - cost_usd) / Decimal(price_usd) * 100).quantize(GP_PLACES)


class StaffQuote(BaseModel):
    """Everything staff need to trust and audit a quote. Never sent to travellers or the LLM.

    Saved with the quote (R5: cost, price, GP%) and linked from the staff page and the trace.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    public: PublicQuote
    cost_lines: tuple[CostLine, ...] = Field(min_length=1)
    fx_lkr_per_usd: Decimal = Field(gt=0, description="FX rate used (Settings tab)")
    cost_lkr: Decimal = Field(ge=0, description="Sum of the LKR parts of the cost lines")
    cost_usd: Decimal = Field(ge=0, description="Whole cost in USD, unrounded: cost_lkr / FX + USD hotel parts")
    margin: Decimal = Field(ge=0, lt=1, description="Margin actually applied (workbook or override)")
    gp_pct: Decimal = Field(description="Gross profit % on the rounded selling price")
    vehicle: str = Field(min_length=1)
    rate_rows: tuple[str, ...] = Field(
        min_length=1, description="Workbook rows used, e.g. 'Tours!row 10 (T09)', 'Hotels!row 50 (H12 Shoulder) 2027-04-12'")

    _check_money = field_validator("fx_lkr_per_usd", "cost_lkr", "cost_usd", "margin", "gp_pct",
                                   mode="before")(_no_floats)

    @model_validator(mode="after")
    def _consistent(self) -> "StaffQuote":
        items = [line.item for line in self.cost_lines]
        if len(items) != len(set(items)):
            raise ValueError("each cost item may appear only once")
        if self.cost_lkr != sum((line.lkr for line in self.cost_lines), Decimal(0)):
            raise ValueError("cost_lkr must equal the sum of the cost lines' LKR")
        usd_parts = sum((line.usd for line in self.cost_lines), Decimal(0))
        if self.cost_usd != self.cost_lkr / self.fx_lkr_per_usd + usd_parts:
            raise ValueError("cost_usd must equal cost_lkr / FX + the USD hotel parts")
        if Decimal(self.public.price_usd) < self.cost_usd:
            raise ValueError("selling price is below cost")
        if self.gp_pct != gross_profit_pct(self.public.price_usd, self.cost_usd):
            raise ValueError("gp_pct does not match price and cost")
        return self


class QuoteResult(BaseModel):
    """What the engine returns: a priced quote, or a hand-off to a specialist. Never both.

    ok               -> staff is set (its .public is what the traveller sees), reasons empty.
    needs_specialist -> at least one reason, and no price anywhere (staff is None).
    The validator makes every other combination impossible to build.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["ok", "needs_specialist"]
    request: QuoteRequest
    staff: StaffQuote | None = None
    reasons: tuple[Refusal, ...] = ()

    @model_validator(mode="after")
    def _one_state_only(self) -> "QuoteResult":
        if self.status == "ok":
            if self.staff is None:
                raise ValueError("status 'ok' needs a priced quote (staff)")
            if self.reasons:
                raise ValueError("status 'ok' cannot have refusal reasons")
            pub = self.staff.public
            if (pub.tour_id, pub.start_date) != (self.request.tour_id, self.request.start_date):
                raise ValueError("the quote's tour and start date must match the request")
        else:
            if not self.reasons:
                raise ValueError("status 'needs_specialist' needs at least one reason")
            if self.staff is not None:
                raise ValueError("status 'needs_specialist' cannot carry a price")
        return self

    @property
    def public(self) -> PublicQuote | None:
        """The only part a traveller or the LLM may see; None when there is no price."""
        return self.staff.public if self.staff else None
