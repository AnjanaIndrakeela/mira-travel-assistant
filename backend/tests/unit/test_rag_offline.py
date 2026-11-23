"""RAG pieces that need no API: chunker (6.2-6.4), BM25 (6.7), FAISS store (6.6), RRF (6.8)."""

import re

import numpy as np
import pytest

from app.data_loader.content_loader import Trust
from app.rag.bm25 import BM25Index, stem, tokenize
from app.rag.chunker import OTHER_AMOUNT_MASK, TOUR_PRICE_MASK, build_chunks, mask_money
from app.rag.embeddings import normalise
from app.rag.index import VectorStore, fingerprint, load_or_build
from app.rag.retriever import asks_about_reviews, asks_about_timing, policy_topics, reciprocal_rank_fusion

MONEY_LEFT = re.compile(r"(USD|LKR|Rs\.?|\$)\s?\d", re.I)


@pytest.fixture(scope="module")
def chunks(content):
    return build_chunks(content)


# 6.2 chunker -----------------------------------------------------------------------------------

def test_chunk_count_and_unique_ids(chunks):
    assert 90 <= len(chunks) <= 130
    assert len({c.id for c in chunks}) == len(chunks)


def test_ids_are_stable(content, chunks):
    assert [c.id for c in build_chunks(content)] == [c.id for c in chunks]


def test_itinerary_days_have_day_ids(chunks):
    ids = {c.id for c in chunks}
    assert {f"T09#day-{n}" for n in range(1, 8)} <= ids
    assert {f"T08#day-{n}" for n in range(1, 9)} <= ids
    assert {f"T07#day-{n}" for n in range(1, 4)} <= ids


def test_every_chunk_starts_with_title_and_section(chunks):
    for c in chunks:
        assert c.text.startswith(f"{c.title} — {c.section}\n\n")


def test_tour_facts_chunk_has_no_teaser_price(chunks):
    facts = next(c for c in chunks if c.id == "T09#facts")
    assert "Duration: 6 nights / 7 days" in facts.text and "Hotel Suisse" in facts.text
    assert "560" not in facts.text and "USD" not in facts.text


# 6.3 published only; trust kept --------------------------------------------------------------

def test_only_published_docs(chunks, content):
    assert not [c for c in chunks if c.doc_id == "T15"]
    assert {c.doc_id for c in chunks} == {d.id for d in content.published()}


def test_testimonials_stay_opinion(chunks):
    p06 = [c for c in chunks if c.doc_id == "P06"]
    assert p06 and all(c.trust is Trust.OPINION for c in p06)
    assert all(c.trust is Trust.FACT for c in chunks if c.doc_id != "P06")


def test_stale_and_expired_flags_kept(chunks):
    t14 = [c for c in chunks if c.doc_id == "T14"]
    assert all(c.stale and c.expired_offer for c in t14)


def test_hidden_comment_never_reaches_a_chunk(chunks, dataset_dir):
    raw = (dataset_dir / "content" / "destinations" / "mirissa.md").read_text(encoding="utf-8")
    comment = re.search(r"<!--(.*?)-->", raw, re.S).group(1).strip()
    assert all(comment[:40] not in c.text for c in chunks)


# 6.4 prices masked ---------------------------------------------------------------------------

def test_no_amounts_left_in_any_chunk(chunks):
    assert [c.id for c in chunks if MONEY_LEFT.search(c.text)] == []


def test_policy_admin_fee_is_masked(chunks):
    multi = next(c for c in chunks if c.id == "P02#multi-day-tours-and-stays")
    assert OTHER_AMOUNT_MASK in multi.text and "50% refund" in multi.text     # percentages stay


@pytest.mark.parametrize("raw", ["From USD 120 per person", "only $35", "LKR 28,000 a night",
                                 "Rs. 5000", "Rs 5,000", "4,500 rupees", "US$ 1,350"])
def test_mask_money_forms(raw):
    masked = mask_money(raw, "tour")
    assert TOUR_PRICE_MASK in masked and not re.search(r"\d{2,}", masked.replace("[price", ""))


def test_mask_keeps_non_money_numbers():
    text = "Day 3: 7 nights, 25% deposit, 48 hours, children under 12"
    assert mask_money(text, "policy") == text


# 6.7 BM25 -------------------------------------------------------------------------------------

def test_place_names_are_kept_whole():
    assert "adams_peak" in tokenize("Adam's Peak sunrise")
    assert "little_adams_peak" in tokenize("Little Adam’s Peak in Ella")
    assert "adams_peak" not in tokenize("Little Adam's Peak")
    assert "galle_fort" in tokenize("the Galle Fort walk") and "nuwara_eliya" in tokenize("Nuwara Eliya")


@pytest.mark.parametrize("word, expected", [
    ("cancellation", "cancel"), ("cancelled", "cancel"), ("cancel", "cancel"), ("kids", "kid"),
    ("tours", "tour"), ("pass", "pass"), ("galle_fort", "galle_fort")])
def test_stem(word, expected):
    assert stem(word) == expected


def test_galle_fort_puts_t04_on_top(chunks):
    top = BM25Index(chunks).search("Galle Fort", k=3)
    assert top[0][0].doc_id == "T04"


def test_adams_peak_has_no_keyword_hit_but_little_adams_peak_does(chunks):
    bm = BM25Index(chunks)
    assert bm.search("Adam's Peak") == []
    assert bm.search("Little Adam's Peak")[0][0].doc_id == "D05"
    assert not bm.has_term("jaffna") and bm.has_term("yala")


# 6.6 FAISS store with fingerprint (fake embedder: no API) -------------------------------------

def fake_embed(texts):
    """Deterministic bag-of-words vectors, so index logic is tested offline."""
    vecs = np.zeros((len(texts), 64), dtype="float32")
    for i, t in enumerate(texts):
        for tok in tokenize(t):
            vecs[i, hash(tok) % 64] += 1
    return normalise(vecs)


def test_store_save_load_and_search(chunks, tmp_path):
    store = VectorStore.build(chunks, fake_embed, model="fake:64")
    store.save(tmp_path)
    loaded = VectorStore.load(tmp_path)
    assert loaded.fingerprint == store.fingerprint and len(loaded.chunks) == len(chunks)
    q = fake_embed(["Galle Fort walking tour"])[0]
    assert [c.id for c, _ in loaded.search(q, 3)] == [c.id for c, _ in store.search(q, 3)]


def test_load_or_build_rebuilds_only_on_change(chunks, tmp_path):
    calls = []
    embed = lambda texts: (calls.append(len(texts)), fake_embed(texts))[1]
    assert load_or_build(chunks, tmp_path, embed=embed, model="fake:64")[1] == "built"
    assert load_or_build(chunks, tmp_path, embed=embed, model="fake:64")[1] == "loaded"
    assert calls == [len(chunks)]
    changed = chunks[:-1] + [chunks[-1].model_copy(update={"text": chunks[-1].text + " edited"})]
    assert load_or_build(changed, tmp_path, embed=embed, model="fake:64")[1] == "built"
    assert load_or_build(changed, tmp_path, embed=embed, model="fake:128")[1] == "built"   # model change


def test_fingerprint_depends_on_text_ids_and_model(chunks):
    fp = fingerprint(chunks, "m")
    assert fp == fingerprint(list(chunks), "m")
    assert fp != fingerprint(chunks, "other") != fingerprint(chunks[1:], "m")


def test_missing_or_broken_index_loads_as_none(tmp_path):
    assert VectorStore.load(tmp_path) is None
    (tmp_path / "meta.json").write_text("{not json", encoding="utf-8")
    assert VectorStore.load(tmp_path) is None


# 6.8 fusion and query helpers -----------------------------------------------------------------

def test_reciprocal_rank_fusion():
    fused = reciprocal_rank_fusion([["a", "b", "c"], ["b", "d"]], k=60)
    assert fused["b"] == pytest.approx(1 / 62 + 1 / 61)
    assert fused["a"] == pytest.approx(1 / 61)
    assert max(fused, key=fused.get) == "b"          # in both lists beats first in one


@pytest.mark.parametrize("query, topics", [
    ("Can I cancel the Galle Fort tour?", ["cancellation"]),
    ("Do kids stay free?", ["children"]),
    ("Can I pay by card?", ["payment"]),
    ("What's the refund if my baby is ill?", ["cancellation", "children"]),
    ("Tell me about Ella", []),
])
def test_policy_topics(query, topics):
    assert policy_topics(query) == topics


def test_review_and_timing_detection():
    assert asks_about_reviews("What do guests say? Any reviews?")
    assert not asks_about_reviews("Tell me about Kandy")
    assert asks_about_timing("Is Yala open in September?") and asks_about_timing("best season for whales")
    assert not asks_about_timing("May I bring my dog?")
