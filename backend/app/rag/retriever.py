"""Hybrid retrieval with policy precedence and an abstain rule (plan §16 step 5, R4).

1. FAISS (meaning) and BM25 (exact names) each rank the chunks; reciprocal rank fusion joins them.
2. Guest reviews (opinion) are dropped unless the question is about reviews.
3. Stale pages and expired offers are demoted.
4. Cancellation, children and payment questions always include the current policy, ranked
   first; tour-page text on the same topic is marked as superseded (traps C3, C4).
5. Abstain instead of guessing (trap C7) when:
   - the question names a place no published page mentions (Jaffna, Adam's Peak), or
   - nothing is semantically close (best cosine below MIN_COSINE), or
   - it asks about a month/season and no retrieved chunk says anything about timing
     (Yala in September).
"""

from __future__ import annotations

import re
from collections.abc import Callable

import numpy as np
from pydantic import BaseModel

from app.data_loader.content_loader import Trust
from app.rag.bm25 import BM25Index, stem, tokenize
from app.rag.chunker import Chunk
from app.rag.index import VectorStore

RRF_K = 60
MIN_COSINE = 0.70
STALE_FACTOR = 0.5

POLICY_TOPICS: dict[str, tuple[str, set[str]]] = {   # topic -> (policy doc, query stems)
    "cancellation": ("P02", {"cancel", "refund", "cancelation"}),
    "children":     ("P03", {"child", "children", "kid", "infant", "baby", "toddler", "teenager"}),
    "payment":      ("P01", {"pay", "payment", "deposit", "balance", "card", "credit", "crypto",
                             "bitcoin", "paypal", "instalment", "installment"}),
}
# Section headings on other pages that the matching policy replaces.
SUPERSEDED_SECTIONS = {"cancellation": re.compile(r"cancel", re.I),
                       "children": re.compile(r"child|kid|famil", re.I),
                       "payment": re.compile(r"payment|deposit", re.I)}
CHILD_TEXT = re.compile(r"\bkids?\b|\bchild(ren)?\b", re.I)

REVIEW_WORDS = {"review", "testimonial", "rating", "feedback", "guest"}

# Places a traveller might name. If one of these is asked about and appears in no published
# chunk, we don't cover it: abstain rather than let similar pages answer for it.
PLACES = {
    "jaffna", "trincomalee", "batticaloa", "arugam_bay", "kalpitiya", "wilpattu", "wilpattu_national_park",
    "adams_peak", "sri_pada", "horton_plains", "haputale", "bentota", "unawatuna", "hikkaduwa",
    "polonnaruwa", "dambulla", "udawalawe", "mirissa", "ella", "kandy", "galle", "galle_fort", "colombo",
    "negombo", "sigiriya", "anuradhapura", "yala", "yala_national_park", "minneriya", "nuwara_eliya",
    "little_adams_peak", "nine_arches_bridge", "nine_arch_bridge", "ella_rock", "knuckles", "kitulgala",
    "pinnawala", "tangalle", "weligama", "matara", "mannar", "delft", "nilaveli", "pasikudah", "ritigala",
    "mihintale", "kataragama", "ratnapura", "pidurangala_rock", "habarana", "kalutara", "beruwala",
}
MONTHS = re.compile(
    r"\b(jan(uary)?|feb(ruary)?|mar(ch)?|apr(il)?|may|june?|july?|aug(ust)?|sep(t(ember)?)?|"
    r"oct(ober)?|nov(ember)?|dec(ember)?|monsoon|season|seasons)\b", re.I)


class RetrievedChunk(BaseModel):
    chunk_id: str
    doc_id: str
    title: str
    section: str
    path: str
    text: str
    trust: Trust
    stale: bool
    score: float               # fused (RRF) score after adjustments
    cosine: float
    bm25: float
    superseded_by: str | None = None   # e.g. "P02" when a policy replaces this text


class Retrieved(BaseModel):
    query: str
    chunks: list[RetrievedChunk]
    abstain: bool
    reason: str | None = None          # unknown_place | low_similarity | no_date_info | no_match
    policy_topics: list[str] = []


def _stems(query: str) -> set[str]:
    return set(tokenize(query)) | {stem(w) for w in re.findall(r"[a-z]+", query.lower())}


def policy_topics(query: str) -> list[str]:
    s = _stems(query)
    return [t for t, (_, words) in POLICY_TOPICS.items() if s & (words | {stem(w) for w in words})]


def asks_about_reviews(query: str) -> bool:
    return bool(_stems(query) & {stem(w) for w in REVIEW_WORDS})


def asks_about_timing(query: str) -> bool:
    """A month or season in the question ("May I..." is not a month)."""
    q = re.sub(r"\bmay\s+(i|we|you)\b", "", query, flags=re.I)
    return bool(MONTHS.search(q))


def reciprocal_rank_fusion(rankings: list[list[str]], k: int = RRF_K) -> dict[str, float]:
    """score(id) = sum over rankings of 1 / (k + rank), rank starting at 1."""
    fused: dict[str, float] = {}
    for ranking in rankings:
        for rank, cid in enumerate(ranking, 1):
            fused[cid] = fused.get(cid, 0.0) + 1.0 / (k + rank)
    return fused


class Retriever:
    def __init__(self, store: VectorStore, embed_query: Callable[[str], np.ndarray]):
        self.store = store
        self.chunks = store.chunks
        self.bm25 = BM25Index(store.chunks)
        self.embed_query = embed_query
        self._by_id = {c.id: i for i, c in enumerate(store.chunks)}
        self._vecs = store.index.reconstruct_n(0, store.index.ntotal)

    def _cosine(self, qvec: np.ndarray, chunk: Chunk) -> float:
        return float(self._vecs[self._by_id[chunk.id]] @ qvec)

    def unknown_places(self, query: str) -> list[str]:
        return [t for t in tokenize(query) if t in PLACES and not self.bm25.has_term(t)]

    def retrieve(self, query: str, *, k: int = 5, tour_id: str | None = None,
                 include_opinion: bool | None = None) -> Retrieved:
        include_opinion = asks_about_reviews(query) if include_opinion is None else include_opinion
        qvec = self.embed_query(query)
        dense = self.store.search(qvec, k=20)
        sparse = self.bm25.search(query, k=20)
        bm25_score = {c.id: s for c, s in sparse}

        fused = reciprocal_rank_fusion([[c.id for c, _ in dense], [c.id for c, _ in sparse]])

        topics = policy_topics(query)
        policy_docs = {POLICY_TOPICS[t][0]: t for t in topics}
        for c in self.chunks:                       # the current policy is always considered
            if c.doc_id in policy_docs:
                fused.setdefault(c.id, 1.0 / (RRF_K + 21))

        results: list[RetrievedChunk] = []
        for cid, score in fused.items():
            c = self.chunks[self._by_id[cid]]
            if c.trust is Trust.OPINION and not include_opinion:
                continue
            if tour_id and c.tour_id not in (None, tour_id):
                continue
            if c.stale or c.expired_offer:
                score *= STALE_FACTOR
            superseded = None
            for topic in topics:
                if c.doc_id != POLICY_TOPICS[topic][0] and c.doc_type != "policy" and (
                        SUPERSEDED_SECTIONS[topic].search(c.section)
                        or (topic == "children" and CHILD_TEXT.search(c.text))):
                    superseded = POLICY_TOPICS[topic][0]
            results.append(RetrievedChunk(
                chunk_id=c.id, doc_id=c.doc_id, title=c.title, section=c.section, path=c.path,
                text=c.text, trust=c.trust, stale=c.stale or c.expired_offer, score=score,
                cosine=self._cosine(qvec, c), bm25=bm25_score.get(c.id, 0.0), superseded_by=superseded))

        # Policy first (best policy chunk per topic), then the rest; superseded text goes last.
        def order(r: RetrievedChunk):
            # policy first; then older text it replaces that the question actually names
            # (shown flagged, so the answer can say which source is current); then the rest
            if r.doc_id in policy_docs:
                return (0, -r.score)
            if r.superseded_by:
                return (1, -r.score) if r.bm25 > 0 else (3, -r.score)
            return (2, -r.score)
        results.sort(key=order)
        policy = [r for r in results if r.doc_id in policy_docs][:3]
        superseded = [r for r in results if r.superseded_by and r.bm25 > 0][:2]
        rest = [r for r in results if r not in policy and not r.superseded_by]
        top = (policy + superseded + rest)[:k]

        abstain, reason = self._abstain(query, top, policy_docs, include_opinion, tour_id)
        return Retrieved(query=query, chunks=top, abstain=abstain, reason=reason, policy_topics=topics)

    def known_places(self, query: str) -> list[str]:
        return [t for t in tokenize(query) if t in PLACES and self.bm25.has_term(t)]

    def _abstain(self, query: str, top: list[RetrievedChunk], policy_docs,
                 include_opinion: bool, tour_id: str | None = None) -> tuple[bool, str | None]:
        if self.unknown_places(query):
            return True, "unknown_place"
        if not top:
            return True, "no_match"
        grounded = (policy_docs or self.known_places(query)
                    or (include_opinion and any(r.trust is Trust.OPINION for r in top))
                    # code matched the tour the question names, and its own pages came back
                    # (a tour title like "Hill Country Tour" names no place)
                    or (tour_id is not None and any(r.doc_id == tour_id and not r.stale for r in top)))
        if max(r.cosine for r in top) < MIN_COSINE and not grounded:
            return True, "low_similarity"
        if asks_about_timing(query) and not any(MONTHS.search(r.text.split("\n\n", 1)[-1]) for r in top):
            return True, "no_date_info"
        return False, None
