"""BM25 keyword search over the same chunks, with place names kept whole.

Multi-word names become one token ("Little Adam's Peak" -> little_adams_peak), so a query for
"Adam's Peak" (adams_peak) does NOT match the Little Adam's Peak page. That is what lets the
retriever abstain on places we don't cover (trap C7).
"""

from __future__ import annotations

import re

from rank_bm25 import BM25Okapi

from app.rag.chunker import Chunk

# Longest first, so "little adam's peak" wins over "adam's peak".
PHRASES = sorted([
    "little adam's peak", "adam's peak", "sri pada", "galle fort", "nuwara eliya", "nine arches bridge",
    "nine arch bridge", "ella rock", "horton plains", "yala national park", "minneriya national park",
    "udawalawe national park", "wilpattu national park", "cultural triangle", "sri lanka",
    "temple of the tooth", "arugam bay", "dambulla cave", "sigiriya rock", "pidurangala rock",
    "kandy lake", "whale watching",
], key=len, reverse=True)

STOP = set("""a an and are as at be but by can could do does for from had has have how i if in into is it
its me my of on or our please so tell than that the their them then there these they this to us
was we what when where which who will with would you your about any also just like want""".split())

_WORD = re.compile(r"[a-z0-9]+")
_PHRASE = re.compile("|".join(re.escape(p) for p in PHRASES))


def _join(m: re.Match) -> str:
    return " " + re.sub(r"[^a-z0-9]+", "_", m.group(0).replace("'", "")) + " "


def stem(word: str) -> str:
    """A deliberately tiny stemmer: cancel/cancelled/cancellation -> cancel, tours -> tour.
    Joined place names (with "_") are never changed."""
    if "_" in word or len(word) <= 3 or word.isdigit():
        return word
    for suffix in ("ations", "ation", "ing", "ed"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            word = word[: -len(suffix)]
            if word.endswith("ll"):
                word = word[:-1]
            return word
    if word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def tokenize(text: str) -> list[str]:
    text = text.lower().replace("’", "'").replace("‘", "'")
    text = _PHRASE.sub(_join, text)
    tokens = re.findall(r"[a-z0-9_]+", text)
    return [stem(t) for t in tokens if t not in STOP and (len(t) > 1 or t.isdigit())]


class BM25Index:
    def __init__(self, chunks: list[Chunk]):
        self.chunks = chunks
        self.docs = [tokenize(c.text) for c in chunks]
        self.vocab = {t for doc in self.docs for t in doc}
        self.bm25 = BM25Okapi(self.docs)

    def search(self, query: str, k: int = 20) -> list[tuple[Chunk, float]]:
        tokens = tokenize(query)
        if not tokens:
            return []
        scores = self.bm25.get_scores(tokens)
        order = sorted(range(len(scores)), key=lambda i: -scores[i])[:k]
        return [(self.chunks[i], float(scores[i])) for i in order if scores[i] > 0]

    def has_term(self, token: str) -> bool:
        return token in self.vocab
