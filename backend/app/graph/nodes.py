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
from app.graph.prompts import load_prompt, system_prompt
from app.graph.state import PER_TURN_DEFAULTS, MiraState, Slot
from app.graph.tours import CatalogTour, catalog, is_place, match_tour, suggest_tours, traveller_type
from app.guards.input_guard import check_input
from app.guards.ui_validator import validate_ui
from app.guards.output_guard import amounts_in, check_output
from app.llm.client import text_of
from app.llm.schemas import GroundedAnswer, TripDetails
from app.llm.structured import invoke_structured
from app.llm.tasks import analyse_turn
from app.pricing import QuoteRequest, calculate_quote
from app.ui.build import choose_components

logger = logging.getLogger("mira.graph")

NO_TOOLS = {"injection", "out_of_scope", "greeting", "handoff"}   # no extraction, no quote
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
                   tours=catalog(ds.content, ds.rates), **overrides)

    def get_retriever(self):
        if self.retriever is None:
            from app.rag import get_retriever
            self.retriever = get_retriever()
        return self.retriever


def _last_human(state: MiraState) -> BaseMessage:
    return next(m for m in reversed(state["messages"]) if m.type == "human")


def _flags(state: MiraState, *new: str) -> list[str]:
    out = list(state.get("flags") or [])
    out += [f for f in new if f not in out]
    return out


class Nodes:
    def __init__(self, deps: Deps):
        self.d = deps
        self.by_id = {t.tour_id: t for t in deps.tours}

    def _models(self, kind: str):
        """None = the real Gemini models (with the switch to the other one built in);
        with test fakes, the same order: this kind first, then the other."""
        fast, strong = self.d.fast_model, self.d.strong_model
        if fast is None and strong is None:
            return None
        pair = [fast, strong] if kind == "fast" else [strong, fast]
        return [m for m in pair if m is not None]

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
        out.update(intent="injection" if r.injection_suspected else r.intent.value,
                   needs_retrieval=r.needs_retrieval, tour_mention=r.tour_mention,
                   trip=r.trip.model_dump(mode="json"))
        if r.injection_suspected:
            out["flags"] = ["injection"]
        if out["intent"] == "injection" and (tid := match_tour(r.tour_mention, self.d.tours)):
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
        tid = match_tour(mention_now, self.d.tours) or match_tour(t.tour_mention, self.d.tours)
        if tid:
            out["selected_tour_id"] = tid
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
        out["children_without_age"] = "child_ages" in t.missing and not (party and party["child_ages"])
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
        """Code decides the next step. Every question counts toward the limit of 3."""
        intent = state["intent"]
        asked = state.get("questions_asked", 0)
        if intent == "injection":
            return {"action": "decline"}
        if intent == "out_of_scope":
            return {"action": "off_topic"}
        if intent == "handoff":
            return {"action": "handoff", "flags": _flags(state, "handoff_requested")}

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
            res = {**out, "action": "match_tours", "flags": _flags(state, *flags)}
            others = [s for s in missing if s != "tour"]
            if others and asked < MAX_QUESTIONS:
                res.update(question=replies.ask_question(others), questions_asked=asked + 1)
            return res

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
        req = QuoteRequest(tour_id=state["selected_tour_id"], start_date=state["start_date"],
                           adults=party["adults"], child_ages=tuple(party["child_ages"]))
        res = calculate_quote(req, rates=self.d.rates, content=self.d.content, today=self.d.today,
                              settings=self.d.settings)
        out: dict = {"quote_request": req.model_dump(mode="json")}
        if res.status == "ok":
            out["quote"] = res.staff.public.model_dump(mode="json")   # PublicQuote only
            return out
        out["refusals"] = [{"code": r.code.value, "message": r.message_traveller} for r in res.reasons]
        out["flags"] = _flags(state, "no_price", *[r.code.value for r in res.reasons])
        return out

    # 8.9 -------------------------------------------------------------------------------
    def match_tours(self, state: MiraState) -> dict:
        interests = list(state.get("interests") or [])
        if state.get("unmatched_tour"):
            interests.append(state["unmatched_tour"])      # "Adam's Peak climb" -> hill country
        cards = suggest_tours(self.d.tours, interests=interests,
                              destinations=state.get("destinations") or [],
                              days=state.get("duration_days"), trip_type=state.get("trip_type"))
        return {"tour_cards": cards, "suggested_tour_ids": [c["tour_id"] for c in cards]}

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
                facts.append("They didn't name a tour, so this is our closest match from the tours "
                             "suggested earlier. Say so, and offer to price another.")
        for msg in dict.fromkeys(r["message"] for r in state.get("refusals") or []):
            facts.append(f"No price can be given: {msg}")
        if name := state.get("unmatched_tour"):
            facts.append(f'They asked about "{name}". We have no such tour in our catalogue. Say so '
                         "plainly, invent nothing about it, and offer to pass the request to our team.")
        if cards := state.get("tour_cards"):
            facts.append("Tours from our catalogue that fit:\n" + replies.tour_list(cards))
        flags = state.get("input_flags") or []
        if "discount_request" in flags:
            facts.append("They asked for a discount: we can't offer discounts in this chat.")
        if "cost_request" in flags:
            facts.append("They asked about internal costs or margins: we never share those.")
        if state["action"] == "match_tours" and not state.get("question") and state.get("missing"):
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
            task = "Suggest the tours listed in the facts, one line each on why they fit."
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
            head = (f"We don't have a tour called \"{state['unmatched_tour']}\" in our programme. "
                    "I can pass your request to our team. Meanwhile, these tours could suit you:"
                    if state.get("unmatched_tour") else "These tours could suit you:")
            return "\n".join(filter(None, [head, replies.tour_list(state.get("tour_cards") or []),
                                           question]))
        if action == "retrieve" and state.get("retrieved"):
            c = state["retrieved"][0]
            return f"Here is what our {c['title']} page says: {c['text'][:400].strip()} [1]"
        return replies.UNKNOWN_INFO

    def _code_reply(self, state: MiraState) -> str:
        """Greeting, quote and refusal turns: fixed wording plus what the traveller raised."""
        parts = [self._fallback(state)]
        if state.get("quote") and state.get("assumed_tour"):
            parts.append("You didn't name a tour, so I priced our closest match. "
                         "I can price any of the other suggestions too.")
        flags = state.get("input_flags") or []
        if "discount_request" in flags:
            parts.append("I can't offer discounts in this chat.")
        if "cost_request" in flags:
            parts.append("I can't share our internal costs.")
        if state.get("quote"):
            parts.append("Would you like to book, or change the dates or travellers?")
        return " ".join(parts)

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
                                    config=config)
            text, cites = ans.answer.strip(), ans.citations
        except Exception as exc:  # noqa: BLE001 (no key, API down, junk twice)
            logger.warning("respond fell back to code wording: %s", exc.__class__.__name__)
            text, cites = "", []
        if not text:
            text = self._fallback(state)
        q = state.get("quote")
        if q and q["price_usd"] not in amounts_in(text):
            text = replies.quote_text(q) + ("\n\n" + text if text else "")     # never lose the price
        n = len(state.get("retrieved") or [])
        return {"response": text, "citations": sorted({c for c in cites if 1 <= c <= n})}

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
                "messages": [AIMessage(content=checked.text)]}

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
