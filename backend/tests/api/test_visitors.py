"""Phase 17A (R2): returning visitors.

- persist remembers the party, traveller type and last quote on the visitor row (17.2)
- a new conversation starts with the known party, so Mira doesn't ask again (17.3, 17.5)
- /visitors/{id}/welcome re-prices the last quote: a new quote row when still valid, and no
  old price when it no longer prices (17.4)
"""

from __future__ import annotations

import uuid
from datetime import date

from app.db.models import Quote, Visitor
from app.db.repo import save_quote
from app.pricing import QuoteRequest, calculate_quote
from tests.api.test_api import S02, api, base, db, engine, quote_s02, s02_model  # noqa: F401  (fixtures)
from tests.unit.test_graph import FakeModel, R, T


def test_persist_remembers_party_type_and_last_quote(api, db):
    quote = quote_s02(api, db)
    visitor = db.query(Visitor).filter(Visitor.last_quote_id == quote.id).one()
    assert visitor.party == {"adults": 2, "child_ages": []}
    assert visitor.traveller_type == "couple"
    assert visitor.last_quote_id == quote.id


def test_new_conversation_starts_with_the_known_party(api, db):
    first = api.use(s02_model()).chat(S02).json()
    # a new conversation, same visitor: names the tour and date only, never the party
    api.use(FakeModel(RouterDecision=[R("quote", "Sigiriya and Minneriya day tour from Kandy")],
                      TripDetails=[T(tour_mention="Sigiriya and Minneriya day tour from Kandy",
                                     start_date=date(2027, 1, 12))]))
    second = api.chat("The Sigiriya and Minneriya day tour from Kandy on 12 January 2027, please.",
                      visitor_id=first["visitor_id"]).json()
    assert second["conversation_id"] != first["conversation_id"]
    assert second["quote_id"], second["message"]                 # priced without asking how many
    q = db.get(Quote, uuid.UUID(second["quote_id"]))
    assert (q.adults, q.child_ages) == (2, [])


def test_new_visitor_is_not_prefilled(api):
    api.use(FakeModel(RouterDecision=[R("quote", "Sigiriya and Minneriya day tour from Kandy")],
                      TripDetails=[T(tour_mention="Sigiriya and Minneriya day tour from Kandy",
                                     start_date=date(2027, 1, 12))]))
    body = api.chat("The Sigiriya and Minneriya day tour from Kandy on 12 January 2027, please.").json()
    assert body["quote_id"] is None                               # asks for the party instead


def test_welcome_re_prices_a_valid_last_quote(api, db):
    quote = quote_s02(api, db)
    visitor = db.query(Visitor).filter(Visitor.last_quote_id == quote.id).one()
    r = api.client.get(f"/api/v1/visitors/{visitor.id}/welcome")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["quote_id"] and body["quote_id"] != str(quote.id)   # a new row
    assert body["ui"] == [{"type": "welcome_back", "tour_title": quote.tour_name, "quote_id": body["quote_id"]}]
    fresh = api.client.get(f"/api/v1/quotes/{body['quote_id']}").json()
    assert fresh["price_usd"] == 315 and "cost" not in str(body).lower()
    assert db.get(Visitor, visitor.id).last_quote_id == uuid.UUID(body["quote_id"])


def test_welcome_never_repeats_an_old_price_that_no_longer_prices(api, db):
    # a quote saved when its date was still ahead; today it is in the past
    old = calculate_quote(QuoteRequest(tour_id="T01", start_date=date(2026, 11, 25), adults=2),
                          today=date(2026, 11, 1))
    assert old.status == "ok"
    row = save_quote(db, old)
    visitor = Visitor(id=uuid.uuid4(), party={"adults": 2, "child_ages": []}, last_quote_id=row.id)
    db.add(visitor)
    db.flush()
    import app.visitors as v
    real = v.calculate_quote
    v.calculate_quote = lambda req, **kw: real(req, today=date(2026, 12, 1))
    try:
        body = api.client.get(f"/api/v1/visitors/{visitor.id}/welcome").json()
    finally:
        v.calculate_quote = real
    assert body["status"] == "needs_specialist" and body["quote_id"] is None
    assert body["ui"] == [{"type": "welcome_back", "tour_title": row.tour_name, "quote_id": None}]
    assert str(row.price_usd) not in body["message"] and "start date has passed" in body["message"]


def test_welcome_for_unknown_or_new_visitor_is_204(api, db):
    assert api.client.get(f"/api/v1/visitors/{uuid.uuid4()}/welcome").status_code == 204
    fresh = Visitor(id=uuid.uuid4())
    db.add(fresh)
    db.flush()
    assert api.client.get(f"/api/v1/visitors/{fresh.id}/welcome").status_code == 204
    assert api.client.get("/api/v1/visitors/not-a-uuid/welcome").status_code == 422
