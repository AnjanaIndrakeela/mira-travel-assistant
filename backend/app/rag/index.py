"""FAISS vector store, saved in backend/var/index/ and rebuilt only when something changed.

The fingerprint is SHA-256 over every chunk (id + text) plus the embedding model and dims, so
a content edit, a chunker change or a model switch triggers a rebuild automatically.

    python -m app.rag.index            # load or build, print status
    python -m app.rag.index --rebuild  # force a rebuild
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import time
from collections.abc import Callable
from pathlib import Path

import faiss
import numpy as np

from app.core.config import VAR_DIR
from app.rag.chunker import Chunk
from app.rag.embeddings import embed_documents, model_id

logger = logging.getLogger("mira.index")

INDEX_DIR = VAR_DIR / "index"


def fingerprint(chunks: list[Chunk], model: str) -> str:
    h = hashlib.sha256(model.encode())
    for c in chunks:
        h.update(b"\0" + c.id.encode() + b"\0" + c.text.encode())
    return h.hexdigest()


class VectorStore:
    def __init__(self, index: faiss.IndexFlatIP, chunks: list[Chunk], fp: str):
        if index.ntotal != len(chunks):
            raise ValueError("index and chunks differ in length")
        self.index, self.chunks, self.fingerprint = index, chunks, fp

    @classmethod
    def build(cls, chunks: list[Chunk], embed: Callable[[list[str]], np.ndarray] = embed_documents,
              model: str | None = None) -> "VectorStore":
        vecs = np.ascontiguousarray(embed([c.text for c in chunks]), dtype="float32")
        index = faiss.IndexFlatIP(vecs.shape[1])           # exact search; ~100 chunks
        index.add(vecs)
        return cls(index, chunks, fingerprint(chunks, model or model_id()))

    def search(self, qvec: np.ndarray, k: int = 20) -> list[tuple[Chunk, float]]:
        q = np.ascontiguousarray(qvec.reshape(1, -1), dtype="float32")
        scores, ids = self.index.search(q, min(k, len(self.chunks)))
        return [(self.chunks[i], float(s)) for s, i in zip(scores[0], ids[0]) if i >= 0]

    def save(self, folder: Path = INDEX_DIR) -> None:
        folder.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self.index, str(folder / "index.faiss"))
        (folder / "chunks.json").write_text(
            json.dumps([c.model_dump(mode="json") for c in self.chunks], ensure_ascii=False), encoding="utf-8")
        (folder / "meta.json").write_text(
            json.dumps({"fingerprint": self.fingerprint, "chunks": len(self.chunks), "dims": self.index.d}),
            encoding="utf-8")

    @classmethod
    def load(cls, folder: Path = INDEX_DIR) -> "VectorStore | None":
        try:
            meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
            chunks = [Chunk(**c) for c in json.loads((folder / "chunks.json").read_text(encoding="utf-8"))]
            return cls(faiss.read_index(str(folder / "index.faiss")), chunks, meta["fingerprint"])
        except (FileNotFoundError, KeyError, ValueError, RuntimeError, json.JSONDecodeError):
            return None


def load_or_build(chunks: list[Chunk], folder: Path = INDEX_DIR, *, rebuild: bool = False,
                  embed: Callable[[list[str]], np.ndarray] = embed_documents,
                  model: str | None = None) -> tuple[VectorStore, str]:
    """Return (store, "loaded" | "built")."""
    fp = fingerprint(chunks, model or model_id())
    if not rebuild and (store := VectorStore.load(folder)) and store.fingerprint == fp:
        logger.info("Vector index loaded, fingerprint unchanged (%d chunks)", len(chunks))
        return store, "loaded"
    t0 = time.perf_counter()
    store = VectorStore.build(chunks, embed, model)
    store.save(folder)
    logger.info("Vector index built: %d chunks in %.1f s", len(chunks), time.perf_counter() - t0)
    return store, "built"


def main(argv: list[str] | None = None) -> None:
    from app.data_loader import get_dataset
    from app.rag.chunker import build_chunks
    ap = argparse.ArgumentParser(prog="python -m app.rag.index")
    ap.add_argument("--rebuild", action="store_true")
    args = ap.parse_args(argv)
    chunks = build_chunks(get_dataset().content)
    t0 = time.perf_counter()
    store, how = load_or_build(chunks, rebuild=args.rebuild)
    print(f"{how}: {len(store.chunks)} chunks in {time.perf_counter() - t0:.1f} s; "
          f"fingerprint {store.fingerprint[:12]}")


if __name__ == "__main__":
    main()
