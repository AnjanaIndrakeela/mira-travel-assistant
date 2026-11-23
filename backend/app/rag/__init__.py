"""Content retrieval (R4): chunker -> Gemini embeddings -> FAISS + BM25 -> hybrid retriever.

get_retriever() loads the saved index (or builds it once) and returns the shared Retriever.
It raises EmbeddingUnavailable when no Gemini key is configured.
"""

from __future__ import annotations

from functools import lru_cache

from app.rag.retriever import Retrieved, RetrievedChunk, Retriever


@lru_cache
def get_retriever() -> Retriever:
    from app.data_loader import get_dataset
    from app.rag.chunker import build_chunks
    from app.rag.embeddings import embed_query
    from app.rag.index import load_or_build
    store, _ = load_or_build(build_chunks(get_dataset().content))
    return Retriever(store, embed_query)


__all__ = ["get_retriever", "Retriever", "Retrieved", "RetrievedChunk"]
