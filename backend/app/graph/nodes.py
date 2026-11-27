"""Mira's graph nodes (plan §6.2, steps 8.2-8.12).

LLM nodes: guard (one call: route + extract) and respond (wording only, and only when code
hasn't got the exact words already).
Code nodes: discovery (merges the extraction), route, price, match_tours, retrieve, build_ui,
persist. Code decides what happens;
the LLM classifies, extracts and phrases. Prices come only from calculate_quote(), and the
output guard checks every reply against the verified numbers before anyone sees it.

Every LLM call has a safe fallback, so a turn always ends with a reply even when Gemini is
down or no key is set.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.graph import replies
from app.graph.persist import persist_turn
from app.visitors import known_slots
from app.graph.prompts import load_prompt, system_prompt
from app.graph.state import PER_TURN_DEFAULTS, MiraState, Slot
from app.graph.quick_parse import quick_analysis
from app.graph.tours import (CatalogTour, is_place, live_tours, match_tour, product_match, suggest_tours,
                             traveller_type)
from app.guards.input_guard import check_input
from app.guards.ui_validator import validate_ui
from app.guards.output_guard import amounts_in, check_output
from app.llm.client import text_of
from app.llm.schemas import GroundedAnswer, TripDetails
from app.llm.structured import invoke_structured
from app.graph.trip_planner import TripPlanner, plan_key
from app.graph.trip_planner import TripPlanner, plan_key
from app.llm.tasks import ANALYSIS_FALLBACK, analyse_turn
from app.pricing import QuoteRequest, calculate_quote
from app.ui.build import choose_components

logger = logging.getLogger("mira.graph")

NO_TOOLS = {"injection", "out_of_scope", "greeting", "handoff"}   # no extraction, no quote

# R6: a price asked for a service we have no rate row for. Code spots it, so the answer never
# depends on the model: no guess, a specialist confirms, and staff get a flagged enquiry.
ASKS_PRICE = re.compile(r"\b(how much|price|prices|cost|costs|rate|rates|quote|charge|fee)\b", re.I)
SERVICES: tuple[tuple[str, str], ...] = (
    (r"airport (?:transfer|pick-?up|drop(?:-?off)?)|(?:transfer|pick-?up|drop-?off) (?:from|to) (?:the )?(?:airport|cmb)",
     "an airport transfer"),
    (r"\btransfers?\b", "a transfer"),
    (r"\b(?:taxi|cab|tuk-?tuk)\b", "a taxi"),
    (r"\b(?:car|van|vehicle) (?:hire|rental)\b|\b(?:hire|rent) a (?:car|van)\b|\bcar with (?:a )?driver\b|\bchauffeur\b",
     "a car with a driver"),
    (r"\b(?:hotel|room|accommodation)s? only\b|\bjust (?:the )?(?:hotel|room|accommodation)\b", "accommodation on its own"),
    (r"\bflights?\b|\bair ?tickets?\b", "flights"),
    (r"\btrain tickets?\b", "train tickets"),
    (r"\bvisa\b(?! card)", "a visa"),
)


def unpriced_service(text: str) -> str | None:
    """The service a price question is about, when it is one we don't sell on its own."""
    if not ASKS_PRICE.search(text):
        return None
    low = text.lower()
    return next((name for pattern, name in SERVICES if re.search(pattern, low)), None)
MAX_QUESTIONS = 3
HISTORY = 8


@contextmanager
def db_scope():
    """The app database: one transaction, committed if the block succeeds."""
    from app.db.session import get_sessionmaker
    with get_sessionmaker()() as session, session.begin():
        yield session


@dataclass
class Deps:
    """Everything the nodes use. Tests pass fakes; None models mean the real Gemini models."""

    today: date
    settings: Settings
    rates: Any
    content: Any
    brand: Any
    tours: list[CatalogTour]
    fast_model: Any = None
    strong_model: Any = None
    retriever: Any = None          # object with .retrieve(); None -> app.rag.get_retriever()
    # () -> context manager yielding a Session that commits on exit; None = don't persist
    session_scope: Callable[[], AbstractContextManager[Session]] | None = None
    extra: dict = field(default_factory=dict)

    @classmethod
    def default(cls, **overrides) -> "Deps":
        from app.data_loader import get_dataset
        settings = overrides.pop("settings", None) or get_settings()
        ds = get_dataset()
        overrides.setdefault("session_scope", db_scope)
        return cls(today=overrides.pop("today", settings.mira_today), settings=settings,
                   rates=ds.rates, content=ds.content, brand=ds.brand,
                   tours=live_tours(ds.content, ds.rates), **overrides)

    def get_retriever(self):
        if self.retriever is None:            # the shared one: re-indexed in place on publish (R8)
            from app.rag import get_retriever
            return get_retriever()
        return self.retriever


def _last_human(state: MiraState) -> BaseMessage:
    return next(m for m in reversed(state["messages"]) if m.type == "human")


CHILD_WORDS = re.compile(r"\b(child|children|kids?|son|sons|daughters?|bab(y|ies)|infants?|toddlers?|teens?|"
                         r"teenagers?|boy|boys|girl|girls|\d{1,2}[- ]?(year|yr)s?[- ]?old)\b", re.IGNORECASE)


def _mentions_child(state: MiraState) -> bool:
    """True if the traveller has written about a child anywhere in this conversation."""
    return any(CHILD_WORDS.search(str(m.content)) for m in state.get("messages") or [] if m.type == "human")


def _flags(state: MiraState, *new: str) -> list[str]:
    out = list(state.get("flags") or [])
    out += [f for f in new if f not in out]
    return out


class Nodes:
    def __init__(self, deps: Deps):
        self.d = deps

    @property
    def by_id(self) -> dict[str, CatalogTour]:
        return {t.tour_id: t for t in self.d.tours}      # the live list: a published tour appears (R8)

    def _models(self, kind: str):
        """None = the real Gemini models (with the switch to the other one built in);
        with test fakes, the same order: this kind first, then the other."""
        fast, strong = self.d.fast_model, self.d.strong_model
        if fast is None and strong is None:
            return None
        pair = [fast, strong] if kind == "fast" else [strong, fast]
        return [m for m in pair if m is not None]

    # 17.3 ------------------------------------------------------------------------------
    def load_visitor(self, state: MiraState) -> dict:
        """First turn of a conversation only: start with what a returning visitor told us last
        time (R2). Interests are reused; last time's party only presets the traveller picker:
        Mira always asks who is travelling before it suggests a plan or a price. The last quote
        itself is re-priced by the welcome endpoint, never copied from the old row."""
        if state.get("is_returning") is not None:
            return {}
        if self.d.session_scope is None or not state.get("visitor_id"):
            return {"is_returning": False}
        try:
            with self.d.session_scope() as session:
                known = known_slots(session, state["visitor_id"])
        except Exception as exc:  # noqa: BLE001  (a database problem: start as a new visitor)
            logger.error("load_visitor failed: %s", exc.__class__.__name__)
            return {"is_returning": False}
        return {k: v for k, v in known.items() if k == "is_returning" or not state.get(k)}

    # 8.2 -------------------------------------------------------------------------------
    def guard(self, state: MiraState, config: RunnableConfig) -> dict:
        """Input guard, then intent. An injection skips the router: no LLM reads it twice."""
        last = _last_human(state)
        check = check_input(text_of(last))
        out: dict = {**PER_TURN_DEFAULTS, "turn": state.get("turn", 0) + 1, "input_flags": check.flags}
        if check.for_log != last.content:     # personal data masked (or text trimmed) for good
            out["messages"] = [HumanMessage(content=check.for_log, id=last.id)]
        if check.injection:
            out.update(intent="injection", flags=["injection"])
            return out
        history = [m for m in state["messages"] if m.id != last.id]
        r = analyse_turn(check.for_log, history, self.d.today, model=self._models("fast"), config=config)
        if r is ANALYSIS_FALLBACK:     # every Gemini model failed: read it with plain rules instead
            if quick := quick_analysis(check.for_log, self.d.tours, self.d.today):
                r = quick
                out["flags"] = ["llm_unavailable"]
                logger.warning("analysis by rules (Gemini unavailable): intent=%s", quick.intent.value)
        out.update(intent="injection" if r.injection_suspected else r.intent.value,
                   needs_retrieval=r.needs_retrieval, tour_mention=r.tour_mention,
                   trip=r.trip.model_dump(mode="json"))
        if r.injection_suspected:
            out["flags"] = ["injection"]
        if out["intent"] == "injection" and (tid := match_tour(r.tour_mention, self.d.tours, check.for_log)):
            out["selected_tour_id"] = tid          # only so the decline can offer a normal quote
        return out

    # 8.3 / 8.4 -------------------------------------------------------------------------
    def discovery(self, state: MiraState) -> dict:
        """Merge the trip details the guard's call extracted; newer values replace older ones.
        Code only: the extraction itself happened in the same Gemini call as the routing."""
        if state["intent"] in NO_TOOLS or not state.get("trip"):
            return {}
        t = TripDetails.model_validate(state["trip"])
        before = (state.get("selected_tour_id"), state.get("start_date"), state.get("party"))
        out: dict = {}

        mention_now = state.get("tour_mention")
        said = str(_last_human(state).content)
        tid = match_tour(mention_now, self.d.tours, said) or match_tour(t.tour_mention, self.d.tours, said)
        if not tid and not mention_now and not t.tour_mention and state["intent"] in {"quote", "book"}:
            tid = product_match(t.interests or [], t.destinations or [], self.d.tours)
        if tid:
            out["selected_tour_id"] = tid
        elif (state["intent"] in {"discovery", "custom_trip"} and not mention_now and not t.tour_mention
              and (t.interests or t.destinations or t.days)):
            # "10 days of beaches and wildlife, what do you suggest?" after a quote: a new trip,
            # so the tour priced earlier is not re-priced for it
            out["selected_tour_id"] = None
        elif (mention_now and state["intent"] in {"quote", "book", "custom_trip", "discovery"}
              and not is_place(mention_now, self.d.tours)):
            out["unmatched_tour"] = mention_now      # a tour we don't have (a place is not one)
        if t.start_date:
            out["start_date"] = t.start_date.isoformat()
        if t.travel_month:
            out["travel_month"] = t.travel_month
        party = state.get("party")
        if t.adults is not None:
            party = {"adults": t.adults, "child_ages": list(t.child_ages)}
        elif t.child_ages and party:
            party = {**party, "child_ages": list(t.child_ages)}
        if party is not None:
            out["party"] = party
        # the LLM sometimes reads "we" or "family" as children; only a child actually mentioned counts
        out["children_without_age"] = ("child_ages" in t.missing and not (party and party["child_ages"])
                                       and _mentions_child(state))
        if t.interests:
            out["interests"] = t.interests
        if t.destinations:
            out["destinations"] = t.destinations
        if t.days:
            out["duration_days"] = t.days

        out["traveller_type"] = traveller_type(party)               # code, never the LLM
        tour = self.by_id.get(out.get("selected_tour_id") or state.get("selected_tour_id") or "")
        days = out.get("duration_days") or state.get("duration_days")
        if state["intent"] == "custom_trip":
            out["trip_type"] = "custom"
        elif tour and tour.kind:
            out["trip_type"] = tour.kind
        elif days:
            out["trip_type"] = "day" if days == 1 else "multi_day"
        after = (out.get("selected_tour_id", before[0]), out.get("start_date", before[1]),
                 out.get("party", before[2]))
        out["slots_changed"] = after != before
        return out

    # 8.5 / 8.6 -------------------------------------------------------------------------
    @staticmethod
    def missing_slots(state: MiraState) -> list[Slot]:
        party = state.get("party")
        missing: list[Slot] = []
        if not state.get("selected_tour_id"):
            missing.append("tour")
        if not state.get("start_date"):
            missing.append("start_date")
        if not party or party["adults"] < 1:
            missing.append("adults")
        if state.get("children_without_age"):
            missing.append("child_ages")
        return missing

    def route(self, state: MiraState) -> dict:
        out = self._route(state)
        # R2: a returning visitor confirms last time's party in one tap instead of typing it again
        last = state.get("remembered_party")
        if last and out.get("question") and "adults" in (out.get("missing") or []):
            who = replies.party_words(last["adults"], len([a for a in last["child_ages"] if a >= 2]),
                                      len([a for a in last["child_ages"] if a < 2]))
            out["question"] += (f" Last time it was {who}; if that's still right, "
                                "tap \"Use these travellers\" below.")
        return out

    def _route(self, state: MiraState) -> dict:
        """Code decides the next step. Every question counts toward the limit of 3."""
        intent = state["intent"]
        asked = state.get("questions_asked", 0)
        if intent == "injection":
            return {"action": "decline"}
        if intent == "out_of_scope":
            return {"action": "off_topic"}
        if intent == "handoff":
            return {"action": "handoff", "flags": _flags(state, "handoff_requested")}
        said = next((str(m.content) for m in reversed(state.get("messages") or []) if m.type == "human"), "")
        if (service := unpriced_service(said)) and not match_tour(state.get("tour_mention"), self.d.tours, said):
            return {"action": "handoff", "unpriced_service": service, "missing": [],
                    "flags": _flags(state, "no_price", "unpriced_service")}

        out: dict = {}
        missing = self.missing_slots(state)
        # "2 adults from 3 May" after we suggested tours: price the top suggestion
        if (missing == ["tour"] and state.get("suggested_tour_ids") and not state.get("unmatched_tour")
                and intent in {"quote", "book", "discovery"}):
            out.update(selected_tour_id=state["suggested_tour_ids"][0], assumed_tour=True)
            missing = []
        out["missing"] = missing

        def ask_or_show(action_if_out_of_questions: str = "match_tours") -> dict:
            if asked < MAX_QUESTIONS:
                return {**out, "action": "ask", "question": replies.ask_question(missing),
                        "questions_asked": asked + 1}
            return {**out, "action": action_if_out_of_questions}      # 8.6: something useful

        if intent == "greeting":
            known = state.get("party") or state.get("selected_tour_id") or state.get("start_date")
            if known and missing:
                return ask_or_show()
            q = replies.FIRST_QUESTION if asked < MAX_QUESTIONS else None
            return {**out, "action": "greet", "question": q, "questions_asked": asked + bool(q)}

        if state.get("unmatched_tour"):
            flags = ["custom_request"] + (["no_price"] if intent in {"quote", "book"} else [])
            return {**out, "action": "match_tours", "flags": _flags(state, *flags)}

        if intent in {"policy", "tour_info"}:
            if not missing and state.get("slots_changed") and intent == "tour_info":
                return {**out, "action": "price"}       # "tell me about X and the price for ..."
            return {**out, "action": "retrieve"}

        if not missing and (intent in {"quote", "book"} or state.get("slots_changed")):
            return {**out, "action": "price"}

        if intent in {"discovery", "custom_trip"} or (
                "tour" in missing and (state.get("interests") or state.get("destinations")
                                       or state.get("duration_days"))):
            flags = ["custom_request"] if intent == "custom_trip" else []
            others = [s for s in missing if s != "tour"]
            if others and asked < MAX_QUESTIONS:
                # Still finding out about the trip: ask, and keep the tours, photos and offers
                # for one organised answer once we know enough (or the 3 questions are used).
                extra = [replies.TRIP_LENGTH] if "tour" in missing and not state.get("duration_days") else []
                # the best matches are picked now (not shown), so "2 adults from 3 May" can be priced
                ids = [c["tour_id"] for c in self._suggest(state)] if "tour" in missing else []
                return {**out, "action": "ask", "flags": _flags(state, *flags),
                        "question": replies.ask_question(others, extra), "questions_asked": asked + 1,
                        **({"suggested_tour_ids": ids} if ids else {})}
            return {**out, "action": "match_tours", "flags": _flags(state, *flags)}

        if missing:
            return ask_or_show()
        return {**out, "action": "retrieve"}

    # 8.7 -------------------------------------------------------------------------------
    def retrieve(self, state: MiraState) -> dict:
        query = text_of(_last_human(state))
        tour_id = state.get("selected_tour_id") if state["intent"] in {"tour_info", "policy"} else None
        try:
            r = self.d.get_retriever().retrieve(query, k=5, tour_id=tour_id)
        except Exception as exc:  # noqa: BLE001 (no key, index missing, API down)
            logger.warning("retrieval failed: %s", exc.__class__.__name__)
            return {"retrieved": [], "abstain_reason": "unavailable",
                    "flags": _flags(state, "unanswered_question")}
        if r.abstain:
            return {"retrieved": [], "abstain_reason": r.reason or "no_match",
                    "flags": _flags(state, "unanswered_question")}
        return {"retrieved": [c.model_dump(mode="json") for c in r.chunks], "abstain_reason": None}

    # 8.8 -------------------------------------------------------------------------------
    def price(self, state: MiraState) -> dict:
        party = state["party"]
        # We chose the tour (the closest match): if it has no price for these dates, try the
        # next match before giving up. A tour the traveller named is never swapped.
        tours = [state["selected_tour_id"]]
        if state.get("assumed_tour"):
            tours += [t for t in state.get("suggested_tour_ids") or [] if t not in tours]
        first: tuple | None = None
        for tour_id in tours[:3]:
            req = QuoteRequest(tour_id=tour_id, start_date=state["start_date"],
                               adults=party["adults"], child_ages=tuple(party["child_ages"]))
            res = calculate_quote(req, rates=self.d.rates, content=self.d.content, today=self.d.today,
                                  settings=self.d.settings)
            if res.status == "ok":
                return {"quote_request": req.model_dump(mode="json"), "selected_tour_id": tour_id,
                        "quote": res.staff.public.model_dump(mode="json")}   # PublicQuote only
            first = first or (req, res)
        req, res = first
        out: dict = {"quote_request": req.model_dump(mode="json")}
        out["refusals"] = [{"code": r.code.value, "message": r.message_traveller} for r in res.reasons]
        out["flags"] = _flags(state, "no_price", *[r.code.value for r in res.reasons])
        return out

    # 8.9 -------------------------------------------------------------------------------
    def _suggest(self, state: MiraState) -> list[dict]:
        interests = list(state.get("interests") or [])
        if not interests and not state.get("destinations"):
            interests = list(state.get("remembered_interests") or [])     # R2: last visit's, as a hint
        if state.get("unmatched_tour"):
            interests.append(state["unmatched_tour"])      # "Adam's Peak climb" -> hill country
        return suggest_tours(self.d.tours, interests=interests,
                             destinations=state.get("destinations") or [],
                             days=state.get("duration_days"), trip_type=state.get("trip_type"))

    def match_tours(self, state: MiraState) -> dict:
        cards = self._suggest(state)
        # show the best match only; the runners-up stay in suggested_tour_ids so a price can fall
        # back to the next one when the best has no rate for those dates
        return {"tour_cards": cards[:1], "suggested_tour_ids": [c["tour_id"] for c in cards]}

    def plan_trip(self, state: MiraState) -> dict:
        """The planner agent: a day-by-day plan for THIS trip, from our published pages (RAG).
        Written once per set of trip details and kept while they stay the same. No price: it is
        a draft our team confirms. If it can't be written safely, the best tour card stays."""
        if state.get("unmatched_tour") or not (state.get("tour_cards") or state.get("assumed_tour")):
            return {}
        key = plan_key(state)
        if state.get("trip_plan") and state.get("trip_plan_key") == key:
            return {"plan_shown": True}
        try:
            retriever = self.d.get_retriever()
        except Exception:  # noqa: BLE001  (no index: plan from the pages alone)
            retriever = None
        plan = TripPlanner(self.d.content, self.d.tours, retriever=retriever,
                           model=self._models("strong")).plan(state)
        if plan is None:
            return {"trip_plan": None, "trip_plan_key": None}
        return {"trip_plan": plan, "trip_plan_key": key, "plan_shown": True}

    # 8.10 ------------------------------------------------------------------------------
    def _facts(self, state: MiraState) -> tuple[str, list[str]]:
        facts: list[str] = []
        tour = self.by_id.get(state.get("selected_tour_id") or "")
        if tour:
            facts.append(f"Tour: {tour.name} ({tour.duration}).")
        if state.get("start_date"):
            facts.append(f"Start date: {replies.nice_date(state['start_date'])}.")
        if party := state.get("party"):
            kids = party["child_ages"]
            facts.append(f"Travellers: {party['adults']} adult(s)"
                         + (f" and children aged {', '.join(map(str, kids))}" if kids else "") + ".")
        if state.get("interests"):
            facts.append(f"Interests: {', '.join(state['interests'])}.")
        if state.get("duration_days"):
            facts.append(f"Wants about {state['duration_days']} days.")
        if q := state.get("quote"):
            facts.append("VERIFIED QUOTE (repeat exactly): " + replies.quote_text(q))
            if state.get("assumed_tour"):
                facts.append("They didn't name a tour, so this is the tour that fits their trip best. "
                             "Say so. Do not list or mention other tours.")
        for msg in dict.fromkeys(r["message"] for r in state.get("refusals") or []):
            facts.append(f"No price can be given: {msg}")
        if name := state.get("unmatched_tour"):
            facts.append(f'They asked about "{name}". We have no such tour in our catalogue. Say so '
                         "plainly, invent nothing about it, and offer to pass the request to our team.")
        if state.get("plan_shown") and (plan := state.get("trip_plan")):
            facts.append(f'I wrote a custom {len(plan["days"])}-day plan for this trip, "{plan["title"]}", '
                         "from our published pages; it is shown below day by day. Say so in one line "
                         "and don't repeat the days. It is a draft: our team will confirm and price it. "
                         "Never give it a price.")
            if cards := state.get("tour_cards"):
                facts.append("The closest published tour, which can be priced and booked now:\n"
                             + replies.tour_list(cards))
        elif cards := state.get("tour_cards"):
            facts.append("The tour from our catalogue that fits best (suggest only this one):\n"
                         + replies.tour_list(cards))
        flags = state.get("input_flags") or []
        if "discount_request" in flags:
            facts.append("They asked for a discount: we can't offer discounts in this chat.")
        if "cost_request" in flags:
            facts.append("They asked about internal costs or margins: we never share those.")
        if state["action"] == "match_tours" and state.get("plan_shown") and state.get("trip_plan"):
            facts.append("Don't ask a question. End by saying the published tour can be priced instantly "
                         "if they'd like it; the custom plan is priced by our team.")
        elif state["action"] == "match_tours" and not state.get("question") and state.get("missing"):
            facts.append("Don't ask a question. Say you can price any of these once they share "
                         + ", ".join(replies.SLOT_WORDS[s] for s in state["missing"]) + ".")
        sources = [f"[{i}] {c['title']} – {c['section']}"
                   + (" (older page)" if c["stale"] else "")
                   + (" (replaced by current policy)" if c.get("superseded_by") else "")
                   + (" (guest opinion)" if c["trust"] == "opinion" else "")
                   + f"\n{c['text']}" for i, c in enumerate(state.get("retrieved") or [], 1)]
        return "\n".join(facts) or "Nothing known about the trip yet.", sources

    def _task(self, state: MiraState) -> str:
        action, question = state["action"], state.get("question")
        if action == "greet":
            return f"Introduce yourself in one sentence and ask: {question}"
        if action == "ask":
            return f"Acknowledge what they said in a few words, then ask this one question: {question}"
        if action == "price":
            task = ("Give the verified quote." if state.get("quote")
                    else "Say a travel specialist will confirm the price. Give no number.")
            if state.get("retrieved"):
                task += " Also answer their other question from the sources."
            return task
        if action == "match_tours":
            task = ("Suggest the tours listed in the facts as a bullet list: one bullet per tour, "
                    "**Tour name**: length and places, then why it fits in a few words.")
            return task + (f" Then ask: {question}" if question else "")
        return "Answer their question from the sources only."

    def _fallback(self, state: MiraState) -> str:
        action, question = state["action"], state.get("question")
        if action == "greet":
            return " ".join(filter(None, [replies.GREETING, question]))
        if action == "ask":
            return question or replies.HANDOFF
        if action == "price":
            if state.get("quote"):
                return replies.quote_text(state["quote"])
            return " ".join(dict.fromkeys(r["message"] for r in state.get("refusals") or [])) \
                or replies.SPECIALIST_PRICE
        if action == "match_tours":
            head = (f"We don't have a tour called \"{state['unmatched_tour']}\" in our programme, "
                    "but I can pass your request to our team. Meanwhile, this tour could suit you:"
                    if state.get("unmatched_tour") else "This tour fits your trip best:")
            if state.get("plan_shown") and (plan := state.get("trip_plan")) and not state.get("unmatched_tour"):
                head = (f"I've drafted a {len(plan['days'])}-day plan for your trip: {plan['title']}. "
                        "It's below, day by day. Our team will confirm it and send you a price. "
                        "If you'd rather book now, this published tour is the closest match:")
            return "\n\n".join(filter(None, [head, replies.tour_list(state.get("tour_cards") or []),
                                             question]))
        if action == "retrieve" and state.get("retrieved"):
            c = state["retrieved"][0]
            return f"Here is what our {c['title']} page says: {c['text'][:400].strip()} [1]"
        return replies.UNKNOWN_INFO

    def _code_reply(self, state: MiraState) -> str:
        """Greeting, quote and refusal turns: fixed wording plus what the traveller raised."""
        parts = [self._fallback(state)]
        if state.get("assumed_tour"):
            name = self.by_id[state["selected_tour_id"]].name if state["selected_tour_id"] in self.by_id else None
            planned = bool(state.get("plan_shown") and state.get("trip_plan"))
            if planned:
                plan = state["trip_plan"]
                parts.insert(0, f"I've drafted a {len(plan['days'])}-day plan for your trip: {plan['title']}. "
                             "It's below; our team will confirm it and send you a price.")
            if state.get("quote"):
                parts.insert(int(planned),
                             f"To book now, the {name} is the closest published tour; I've priced it."
                             if name and planned else
                             f"The {name} fits your trip best, so I've priced it." if name
                             else "I've priced the tour that fits your trip best.")
            elif planned:
                # no instant price for the closest tour either: one line, not the refusal as well
                parts[1:] = [f"Under it is the closest published tour{f', the {name}' if name else ''}. "
                             "It has no instant price for those dates, so our team will price both and "
                             "get back to you."]
            elif state.get("suggested_tour_ids"):
                parts.append("This is the tour that fits your trip best; a specialist can confirm a price "
                             "for it.")
        flags = state.get("input_flags") or []
        if "discount_request" in flags:
            parts.append("I can't offer discounts in this chat.")
        if "cost_request" in flags:
            parts.append("I can't share our internal costs.")
        if state.get("quote"):
            parts.append("Would you like to book, or change the dates or travellers?")
        return "\n\n".join(parts)

    def respond(self, state: MiraState, config: RunnableConfig) -> dict:
        action = state["action"]
        if action == "decline":
            tour = self.by_id.get(state.get("selected_tour_id") or "")
            ask = (f" Shall I price the {tour.name} for you? Tell me your start date and who is travelling."
                   if tour else " Which tour would you like a price for?")
            return {"response": replies.DECLINE + ask, "citations": []}
        if action == "off_topic":
            return {"response": replies.OFF_TOPIC, "citations": []}
        if action == "handoff":
            if service := state.get("unpriced_service"):
                return {"response": replies.service_price(service), "citations": []}
            return {"response": replies.HANDOFF, "citations": []}
        if action == "retrieve" and not state.get("retrieved"):
            return {"response": replies.UNKNOWN_INFO, "citations": []}
        # Code already has the exact words: no Gemini call (fewer calls, no quota, no 503)
        if action == "greet" or (action == "price" and not state.get("retrieved")):
            return {"response": self._code_reply(state), "citations": []}

        facts, sources = self._facts(state)
        last = _last_human(state)
        history = [m for m in state["messages"] if m.id != last.id][-HISTORY:]
        prompt = load_prompt("respond", task=self._task(state), facts=facts,
                             sources="\n\n".join(sources) or "(none)", message=text_of(last))
        msgs = [SystemMessage(content=system_prompt(self.d.today, self.d.brand)), *history,
                HumanMessage(content=prompt)]
        try:   # strong model; invoke_structured retries and switches to the fast one if needed
            ans = invoke_structured(GroundedAnswer, msgs, kind="strong", model=self._models("strong"),
                                    config=config, name="write-answer")
            text, cites = ans.answer.strip(), ans.citations
            abstained = ans.abstained and action == "retrieve"
        except Exception as exc:  # noqa: BLE001 (no key, API down, junk twice)
            logger.warning("respond fell back to code wording: %s", exc.__class__.__name__)
            text, cites, abstained = "", [], False
        if not text:
            text = self._fallback(state)
            if action == "retrieve" and state.get("retrieved"):
                cites = [1]          # the fallback quotes the top page and marks it [1]
        q = state.get("quote")
        if q and q["price_usd"] not in amounts_in(text):
            text = replies.quote_text(q) + ("\n\n" + text if text else "")     # never lose the price
        n = len(state.get("retrieved") or [])
        out = {"response": text, "citations": sorted({c for c in cites if 1 <= c <= n})}
        if abstained:           # the pages found don't answer it: offer the team, as for no pages
            out["abstain_reason"] = "not_in_sources"
        return out

    # 8.11 ------------------------------------------------------------------------------
    def build_ui(self, state: MiraState) -> dict:
        q = state.get("quote")
        verified = [q["price_usd"], q["deposit_usd"], q["balance_usd"]] if q else []
        checked = check_output(state.get("response") or "", verified)
        flags = _flags(state, *(["output_guard"] if checked.changed else []))
        # code picks components from verified facts; the validator drops anything off-catalog
        ui, rejected = validate_ui(choose_components(state, content=self.d.content, rates=self.d.rates),
                                   quote_id=state.get("quote_id"))
        if rejected:
            flags = _flags({"flags": flags}, "ui_rejected")
        return {"response": checked.text, "ui": ui, "ui_rejected": rejected, "flags": flags,
                "messages": [AIMessage(content=checked.text)], "ui_log": [ui]}

    # 8.12 ------------------------------------------------------------------------------
    def persist(self, state: MiraState) -> dict:
        """Save the quote, its enquiry and the trace ID (9.3-9.4). Runs before build_ui so the
        quote card can carry the quote_id. A database problem is logged, never shown: the
        traveller still gets the reply (the quote card then has no quote_id to book with)."""
        logger.info("turn %s thread=%s action=%s flags=%s quote=%s", state.get("turn"),
                    state.get("thread_id"), state["action"], state.get("flags"),
                    bool(state.get("quote")))
        if self.d.session_scope is None:
            return {}
        try:
            with self.d.session_scope() as session:
                return persist_turn(session, state, self.d)
        except Exception as exc:  # noqa: BLE001
            logger.error("persist failed: %s", exc.__class__.__name__)
            return {"flags": _flags(state, "not_saved")}
