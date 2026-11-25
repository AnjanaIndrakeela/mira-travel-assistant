"""Content retrieval (R4): chunker -> Gemini embeddings -> FAISS + BM25 -> hybrid retriever.

get_retriever() loads the saved index (or builds it once) and returns the shared Retriever.
It raises EmbeddingUnavailable when no Gemini key is configured.

R8: content an approver published lives in the database (path "db/..."), never in the dataset.
The saved index covers the dataset only (so its fingerprint stays stable); published items are
added on top by embedding just their chunks, at startup and on every publish (add_docs()).
"""

from __future__ import annotations

import logging
import threading

from app.rag.retriever import Retrieved, RetrievedChunk, Retriever

logger = logging.getLogger("mira.rag")
DB_PREFIX = "db/"                 # ContentDoc.path of content that came from content_items

_lock = threading.Lock()
_retriever: Retriever | None = None


def _extend(store, docs):
    """A new VectorStore: the old vectors plus the chunks of `docs` (only those are embedded)."""
    import faiss
    import numpy as np

    from app.rag.chunker import chunks_for_doc
    from app.rag.embeddings import embed_documents
    from app.rag.index import VectorStore
    ids = {d.id for d in docs}
    keep = [i for i, c in enumerate(store.chunks) if c.doc_id not in ids]      # re-publish replaces
    new = [c for d in docs if d.is_published for c in chunks_for_doc(d)]
    old = store.index.reconstruct_n(0, store.index.ntotal)[keep] if keep else np.zeros((0, store.index.d), "float32")
    vecs = np.ascontiguousarray(np.vstack([old, embed_documents([c.text for c in new])]) if new else old,
                                dtype="float32")
    index = faiss.IndexFlatIP(store.index.d)
    if len(vecs):
        index.add(vecs)
    return VectorStore(index, [store.chunks[i] for i in keep] + new, store.fingerprint + f"+{len(new)}")


def get_retriever() -> Retriever:
    global _retriever
    with _lock:
        if _retriever is None:
            from app.data_loader import get_dataset
            from app.data_loader.content_loader import ContentLibrary
            from app.rag.chunker import build_chunks
            from app.rag.embeddings import embed_query
            from app.rag.index import load_or_build
            lib = get_dataset().content
            base = ContentLibrary(docs=[d for d in lib.docs if not d.path.startswith(DB_PREFIX)])
            store, _ = load_or_build(build_chunks(base))
            extra = [d for d in lib.published() if d.path.startswith(DB_PREFIX)]
            if extra:
                store = _extend(store, extra)
                logger.info("Index: %d published content item(s) added on top of the dataset", len(extra))
            _retriever = Retriever(store, embed_query)
        return _retriever


def add_docs(docs) -> None:
    """Re-index on publish: the next retrieve() sees the new docs. No-op if not built yet
    (it will include them when it is, since they're in the content library by then)."""
    global _retriever
    with _lock:
        if _retriever is not None:
            from app.rag.embeddings import embed_query
            _retriever = Retriever(_extend(_retriever.store, list(docs)), embed_query)


def reset() -> None:
    global _retriever
    with _lock:
        _retriever = None


__all__ = ["get_retriever", "add_docs", "reset", "Retriever", "Retrieved", "RetrievedChunk", "DB_PREFIX"]
