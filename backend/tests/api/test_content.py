"""Phase 17B (R8): the content agent drafts, only an approver publishes, publishing re-indexes.

No Gemini calls: the content agent gets scripted fake models, and the re-index test uses fake
embeddings. Everything that touches the shared in-memory library is undone after each test.
"""

from __future__ import annotations

import uuid
from datetime import date

import numpy as np
import pytest

from app.data_loader import get_dataset
from app.db.models import ContentItem
from app.graph.content_workflow import (ContentFlow, ContentPlan, DraftDay, TourDraft, go_live, rule_plan,
                                        to_content_doc)
from app.graph.tours import match_tour, refresh_live_tours, live_tours
from app.pricing import QuoteRequest, calculate_quote
from tests.api.test_api import api, base, db, engine  # noqa: F401  (fixtures)
from tests.api.test_staff import fresh_limiter, login, users  # noqa: F401
from tests.unit.test_graph import FakeModel

COMMAND = "Add a 5-day Hill Country tour using the Ella photos"
PLAN = ContentPlan(title="5-Day Hill Country Tour", days=5, places=["ella", "nuwara-eliya", "kandy"], media_tag="ella")


def draft(days=5, extra="") -> TourDraft:
    names = ["Kandy", "Kandy to Nuwara Eliya", "Nuwara Eliya", "Nuwara Eliya to Ella", "Ella"]
    return TourDraft(title="Misty Hills of Ella and Kandy", overview="Tea country, temples and hill walks." + extra,
                     days=[DraftDay(day=i + 1, title=names[i % 5], description=f"A day in {names[i % 5]}.")
                           for i in range(days)])


@pytest.fixture
def writer(monkeypatch):
    """Scripted content agent: set writer.out to the TourDraft the 'LLM' returns."""
    class W:
        out = draft()

    def make(content, media, model=None):
        return ContentFlow(content, media, model=FakeModel(ContentPlan=[PLAN], TourDraft=[W.out]))
    monkeypatch.setattr("app.api.content.ContentFlow", make)
    return W


@pytest.fixture
def library():
    """Restore the shared content library, tour catalog and retriever after the test."""
    import app.rag as rag
    ds = get_dataset()
    docs, retriever = list(ds.content.docs), rag._retriever
    yield ds
    ds.content.docs[:] = docs
    refresh_live_tours(ds.content, ds.rates)
    rag._retriever = retriever


@pytest.fixture
def no_reindex(monkeypatch):
    published = []
    monkeypatch.setattr("app.api.content.go_live", lambda docs: published.extend(docs))
    return published


# ---- 17.7 plan -> draft -> validate -> save (draft forced) --------------------------------------------

def test_rule_plan_reads_the_command():
    ds = get_dataset()
    flow = ContentFlow(ds.content, [{"id": "m", "tag": "ella", "path": "ella/x.svg", "alt": "x"}])
    p = rule_plan(COMMAND, flow.places, flow.tags)
    assert (p.days, p.media_tag) == (5, "ella") and set(p.places) == {"ella", "nuwara-eliya", "kandy"}
    assert rule_plan("A 4-night beach tour", flow.places, flow.tags).days == 5


def test_staff_command_creates_a_draft_with_ella_pictures(api, db, users, writer, library):
    login(api, users, "staff")
    r = api.client.post("/api/v1/staff/content", json={"command": COMMAND})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "draft" and body["doc_id"] is None and body["days"] == 5
    assert body["media"] and all(m["url"].startswith("/api/v1/media/ella/") for m in body["media"])
    assert "### Day 5: Ella" in body["body"] and body["sources"]
    assert api.client.get(body["media"][0]["url"]).status_code == 200            # the preview loads
    # a draft is not in the library: never retrieved, matched or priced
    assert not any(d.title == body["title"] for d in library.content.docs)
    assert match_tour(body["title"], live_tours(library.content, library.rates)) is None


@pytest.mark.parametrize("bad,why", [
    (draft(4), "expected 1 to 5"),
    (draft(extra=" Only USD 499 per person!"), "not allowed"),
    (draft(extra=" Then on to Jaffna."), "Jaffna"),
])
def test_validation_stops_bad_drafts(api, db, users, writer, bad, why):
    writer.out = bad
    login(api, users, "staff")
    before = db.query(ContentItem).count()
    r = api.client.post("/api/v1/staff/content", json={"command": COMMAND})
    assert r.status_code == 422 and why in r.json()["message"]
    assert db.query(ContentItem).count() == before                                  # nothing saved


def test_the_llm_cannot_set_the_status():
    assert "status" not in TourDraft.model_fields and "status" not in ContentPlan.model_fields


# ---- 17.9 only an approver can publish ----------------------------------------------------------------

def test_staff_gets_403_and_approver_publishes(api, db, users, writer, no_reindex):
    login(api, users, "staff")
    item = api.client.post("/api/v1/staff/content", json={"command": COMMAND}).json()
    assert api.client.post(f"/api/v1/staff/content/{item['id']}/publish").status_code == 403
    assert api.client.post(f"/api/v1/staff/content/{item['id']}/reject", json={}).status_code == 403
    api.client.post("/api/v1/auth/logout")
    assert api.client.post(f"/api/v1/staff/content/{item['id']}/publish").status_code == 401
    login(api, users, "approver")
    r = api.client.post(f"/api/v1/staff/content/{item['id']}/publish")
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["status"] == "published" and out["doc_id"].startswith("T") and out["approved_by"] == users["approver"][0]
    assert [d.id for d in no_reindex] == [out["doc_id"]]
    assert api.client.post(f"/api/v1/staff/content/{item['id']}/publish").status_code == 409   # only once


def test_reject(api, db, users, writer):
    login(api, users, "staff")
    item = api.client.post("/api/v1/staff/content", json={"command": COMMAND}).json()
    login(api, users, "approver")
    r = api.client.post(f"/api/v1/staff/content/{item['id']}/reject", json={"note": "Too short"})
    assert r.json()["status"] == "rejected" and r.json()["review_note"] == "Too short"


def test_travellers_cannot_reach_content_routes(api):
    assert api.client.get("/api/v1/staff/content").status_code == 401
    assert api.client.post("/api/v1/staff/content", json={"command": COMMAND}).status_code == 401
    assert api.client.get("/api/v1/media/ella/../../app/main.py").status_code == 404


# ---- 17.10 / 17.11 publish -> retrievable, matchable, and priced only by a specialist ------------------

def test_publishing_re_indexes_and_the_price_goes_to_a_specialist(db, library, monkeypatch):
    import app.rag as rag
    from app.core.config import get_settings
    from app.rag.chunker import build_chunks
    from app.rag.index import VectorStore
    from app.rag.retriever import Retriever
    dims = get_settings().gemini_embedding_dims
    rng = np.random.default_rng(0)

    def fake_embed(texts):
        v = rng.normal(size=(len(texts), dims)).astype("float32")
        return v / np.linalg.norm(v, axis=1, keepdims=True)
    monkeypatch.setattr("app.rag.embeddings.embed_documents", fake_embed)
    base_lib = type(library.content)(docs=list(library.content.docs))
    rag._retriever = Retriever(VectorStore.build(build_chunks(base_lib), fake_embed, "fake"),
                               lambda q: fake_embed([q])[0])

    item = ContentItem(status="published", type="tour", title="Misty Hills of Ella and Kandy",
                       body="# Misty Hills of Ella and Kandy\n\nTea country.\n\n### Day 1: Kandy\n\nTemple of the Tooth.\n",
                       data={"doc_id": "T97", "days": 5, "places": ["ella", "kandy"]}, created_by=uuid.uuid4())
    doc = to_content_doc(item)
    assert doc.id not in {c.doc_id for c in rag.get_retriever().chunks}
    go_live([doc])
    r = rag.get_retriever()
    assert {"T97#day-1", "T97#facts"} & {c.id for c in r.chunks}                  # re-indexed
    assert r.bm25.has_term("misti") or r.bm25.has_term("misty")
    assert match_tour("Misty Hills of Ella and Kandy", live_tours(library.content, library.rates)) == "T97"
    q = calculate_quote(QuoteRequest(tour_id="T97", start_date=date(2027, 3, 1), adults=2))
    assert q.status == "needs_specialist" and q.staff is None
    assert [x.code.value for x in q.reasons] == ["no_rate_row"]
