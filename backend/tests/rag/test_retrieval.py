"""Retrieval on the real index with Gemini query embeddings (6.9-6.13).

Needs GEMINI_API_KEY. Query vectors are cached in backend/var/index/query_cache.json, so after
the first run these tests make no API calls.
"""

import pytest

from app.core.config import get_settings
from app.data_loader.content_loader import Trust

pytestmark = pytest.mark.skipif(get_settings().gemini_api_key is None, reason="needs GEMINI_API_KEY")


@pytest.fixture(scope="module")
def retriever():
    from app.rag import get_retriever
    return get_retriever()


def ids(result):
    return [c.chunk_id for c in result.chunks]


def docs(result):
    return [c.doc_id for c in result.chunks]


# tour detail, destination, policy --------------------------------------------------------------

def test_itinerary_day(retriever):
    r = retriever.retrieve("What's included on day 3 of the Cultural Triangle tour?")
    assert not r.abstain and "T09#day-3" in ids(r)[:3]


def test_destination(retriever):
    r = retriever.retrieve("Tell me about Ella")
    assert not r.abstain and docs(r)[0] == "D05"


def test_cancellation_policy(retriever):
    r = retriever.retrieve("What is your cancellation policy?")
    assert not r.abstain and docs(r)[0] == "P02"


def test_polonnaruwa_comes_from_tour_pages(retriever):
    """No destination page exists (C8): answer from T08/T09/T16 itineraries only."""
    r = retriever.retrieve("Tell me about Polonnaruwa.")
    assert not r.abstain
    assert set(docs(r)[:3]) <= {"T08", "T09", "T16"}


def test_faq(retriever):
    r = retriever.retrieve("Can you cater for vegetarians?")
    assert ids(r)[0] == "P04#can-you-cater-for-dietary-needs"


# 6.9 policy precedence ---------------------------------------------------------------------------

def test_galle_cancellation_policy_beats_tour_page(retriever):
    """C3/S08: P02 (48 h, current) ranks above T04's old 24 h line, which is flagged."""
    r = retriever.retrieve("Can I cancel the Galle Fort walking tour the day before?")
    assert docs(r)[0] == "P02"
    if "T04#cancellation" in ids(r):
        t04 = next(c for c in r.chunks if c.chunk_id == "T04#cancellation")
        assert t04.superseded_by == "P02"
        assert ids(r).index("T04#cancellation") > ids(r).index("P02#day-and-city-tours")


def test_kids_stay_free_is_answered_by_the_children_policy(retriever):
    """C4/S07: T07's old 'kids under 12 stay free' is superseded by P03."""
    r = retriever.retrieve("Do kids under 12 stay free on the Kandy Heritage Stay?")
    assert docs(r)[0] == "P03"
    claim = next(c for c in r.chunks if "kids under 12 stay free" in c.text)
    assert claim.chunk_id == "T07#overview" and claim.superseded_by == "P03"
    # other T07 text (e.g. day 1) says nothing about children and is not flagged
    assert all(c.superseded_by is None for c in r.chunks if c.doc_id == "T07" and "kid" not in c.text.lower())


def test_payment_policy(retriever):
    r = retriever.retrieve("Can I pay with crypto?")
    assert ids(r)[0] == "P01#payment"


def test_stale_pages_rank_below_current_ones(retriever):
    r = retriever.retrieve("Cultural Triangle tour Sigiriya Polonnaruwa Kandy")
    assert docs(r).index("T09") < docs(r).index("T16") if "T16" in docs(r) else True
    assert all(c.stale for c in r.chunks if c.doc_id in {"T16", "T14", "T07", "T06"})


# 6.10 abstain -------------------------------------------------------------------------------------

@pytest.mark.parametrize("query, reason", [
    ("Do you do tours to Jaffna?", "unknown_place"),                         # S10
    ("Do you do an Adam's Peak sunrise climb? How much is it?", "unknown_place"),   # S16
    ("Is Yala open in September?", "no_date_info"),                         # S09
    ("What is the weather in Paris?", "low_similarity"),
    ("May I bring my dog?", "low_similarity"),
])
def test_abstains(retriever, query, reason):
    r = retriever.retrieve(query)
    assert r.abstain and r.reason == reason


@pytest.mark.parametrize("query", [
    "Do you have a tour to Little Adam's Peak?", "When can I see whales in Mirissa?",
    "Can I see whales in August?", "Galle Fort", "Do you offer airport transfers?",
])
def test_answerable_questions_do_not_abstain(retriever, query):
    assert not retriever.retrieve(query).abstain


# 6.11 opinions only when asked -------------------------------------------------------------------

def test_reviews_are_returned_when_asked(retriever):
    r = retriever.retrieve("What do your guests say about you?")
    assert not r.abstain and r.chunks[0].trust is Trust.OPINION


@pytest.mark.parametrize("query", ["Is there a discount for anniversaries?", "Can I see whales in August?",
                                   "Tell me about Mirissa"])
def test_opinions_never_answer_fact_questions(retriever, query):
    assert all(c.trust is Trust.FACT for c in retriever.retrieve(query).chunks)


# 6.12 / 6.13 shape, drafts ------------------------------------------------------------------------

def test_result_shape(retriever):
    c = retriever.retrieve("Tell me about Kandy").chunks[0]
    assert set(c.model_dump()) == {"chunk_id", "doc_id", "title", "section", "path", "text", "trust",
                                   "stale", "score", "cosine", "bm25", "superseded_by"}
    assert c.path.startswith("content/") and c.chunk_id.startswith(c.doc_id + "#")


@pytest.mark.parametrize("query", ["Northern Sri Lanka Tour", "Jaffna and the north", "Tell me about the new northern tour"])
def test_draft_is_never_returned(retriever, query):
    assert "T15" not in docs(retriever.retrieve(query, k=20))


def test_tour_filter(retriever):
    r = retriever.retrieve("What is included?", tour_id="T09")
    assert set(docs(r)) <= {"T09", "P01", "P02", "P03", "P04", "P05", "D01", "D02", "D03", "D04",
                            "D05", "D06", "D07", "D08", "D09", "D10"}
    assert "T09" in docs(r)


def test_no_amounts_reach_the_results(retriever):
    import re
    for q in ["How much is the Galle Fort tour?", "Price of Treasures of Sri Lanka", "cancellation fee"]:
        for c in retriever.retrieve(q).chunks:
            assert not re.search(r"(USD|LKR|\$)\s?\d", c.text)
