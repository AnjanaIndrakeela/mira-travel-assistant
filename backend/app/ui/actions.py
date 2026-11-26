"""A2UI v1.0 actions from the browser (step 7 of the A2UI move).

A click on a card (Get a price, the traveller picker's Send, Get a new quote...) comes back as an
A2UI `action` message instead of free text:

  {"version": "1.0", "action": {"name": "get_price", "surfaceId": "reply-2-...",
   "sourceComponentId": "c1", "timestamp": "...", "context": {"tour_id": "T03"}}}

Only the actions below exist, each with a typed context, so a bad or unknown action is rejected
(422) before the graph runs. The server, not the browser, writes the traveller's message for the
action, and that message then goes through the same input guard and graph as anything typed.
The booking and enquiry forms are NOT actions: they post to their own endpoints, so card and
contact details never travel through the chat.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.ui.export import A2UI_VERSION

TourId = Annotated[str, Field(pattern=r"^T\d{2}$")]


class _Ctx(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TourContext(_Ctx):
    tour_id: TourId


class TravellersContext(_Ctx):
    adults: int = Field(ge=1, le=20)
    child_ages: list[Annotated[int, Field(ge=0, le=17)]] = Field(default_factory=list, max_length=10)


class NoContext(_Ctx):
    pass


# action name -> (the component it comes from, its context)
ACTIONS: dict[str, tuple[str, type[_Ctx]]] = {
    "get_price": ("TourCard", TourContext),
    "ask_team": ("TourCard", TourContext),
    "set_travellers": ("TravellerPicker", TravellersContext),
    "new_quote": ("BookingForm", NoContext),
    "packing_tips": ("BookingForm", NoContext),
    "plan_another": ("BookingForm", NoContext),
}


class A2uiAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Literal["get_price", "ask_team", "set_travellers", "new_quote", "packing_tips", "plan_another"]
    surfaceId: str = Field(min_length=1, max_length=80)
    sourceComponentId: str = Field(min_length=1, max_length=80)
    timestamp: str | None = Field(default=None, max_length=40)
    context: dict = Field(default_factory=dict)


class A2uiActionMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal["1.0"] = A2UI_VERSION
    action: A2uiAction

    def checked_context(self) -> _Ctx:
        """The context validated for this action (raises pydantic.ValidationError)."""
        return ACTIONS[self.action.name][1].model_validate(self.action.context)


def _tour(tour_id: str) -> str:
    from app.graph.tours import tour_name
    name = tour_name(tour_id)
    return f"the {name} ({tour_id})" if name else f"tour {tour_id}"


def action_text(msg: A2uiActionMessage) -> str:
    """The traveller's message for an action, written here on the server."""
    ctx = msg.checked_context()
    name = msg.action.name
    if name == "get_price":
        return f"I'd like a price for {_tour(ctx.tour_id)}."
    if name == "ask_team":
        return f"Can your team help me with {_tour(ctx.tour_id)}?"
    if name == "set_travellers":
        people = f"{ctx.adults} adult{'' if ctx.adults == 1 else 's'}"
        ages = ctx.child_ages
        kids = (f" and {len(ages)} child{'' if len(ages) == 1 else 'ren'} aged {', '.join(map(str, ages))}"
                if ages else " and no children")
        return f"We are {people}{kids}."
    return {"new_quote": "Please give me a new quote for this trip.",
            "packing_tips": "What should I pack for this trip?",
            "plan_another": "I'd like to plan another trip."}[name]
