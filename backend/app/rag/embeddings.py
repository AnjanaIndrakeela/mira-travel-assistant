"""Gemini embeddings (plan §16 step 2): text -> unit-length 768-number vectors.

Lessons from the first LLM trial, kept here so they aren't relearned:
- Each text must be wrapped in its own types.Content; a plain list of strings is merged into
  ONE content and returns ONE vector.
- Keep the genai.Client alive (module-level cache); a closed client fails the next call.
- Vectors cut to 768 dims are not unit length: L2-normalise, so inner product = cosine.
- Documents and queries use different task types.
Query vectors are cached on disk too, so repeated eval questions cost nothing.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from functools import lru_cache
from pathlib import Path

import numpy as np

from app.core.config import VAR_DIR, get_settings

logger = logging.getLogger("mira.embeddings")

BATCH = 50
QUERY_CACHE = VAR_DIR / "index" / "query_cache.json"
_lock = threading.Lock()


class EmbeddingUnavailable(RuntimeError):
    """No API key, or the embedding service failed after retries."""


@lru_cache
def _client():
    from google import genai
    key = get_settings().gemini_api_key
    if key is None:
        raise EmbeddingUnavailable("GEMINI_API_KEY is not set")
    return genai.Client(api_key=key.get_secret_value())


def model_id() -> str:
    s = get_settings()
    return f"{s.gemini_embedding_model}:{s.gemini_embedding_dims}"


def normalise(v: np.ndarray) -> np.ndarray:
    v = np.asarray(v, dtype="float32")
    norms = np.linalg.norm(v, axis=-1, keepdims=True)
    return v / np.where(norms == 0, 1, norms)


def _embed(texts: list[str], task: str, retries: int = 3) -> np.ndarray:
    from google.genai import types
    s = get_settings()
    out: list[list[float]] = []
    for start in range(0, len(texts), BATCH):
        batch = texts[start:start + BATCH]
        contents = [types.Content(parts=[types.Part(text=t)]) for t in batch]
        for attempt in range(retries):
            try:
                r = _client().models.embed_content(
                    model=s.gemini_embedding_model, contents=contents,
                    config=types.EmbedContentConfig(task_type=task,
                                                    output_dimensionality=s.gemini_embedding_dims))
                break
            except Exception as exc:  # noqa: BLE001
                if attempt == retries - 1:
                    raise EmbeddingUnavailable(f"embedding failed: {exc.__class__.__name__}") from exc
                time.sleep(2 ** attempt)
        if len(r.embeddings) != len(batch):
            raise EmbeddingUnavailable(f"asked for {len(batch)} vectors, got {len(r.embeddings)}")
        out.extend(e.values for e in r.embeddings)
    return normalise(np.asarray(out, dtype="float32"))


def embed_documents(texts: list[str]) -> np.ndarray:
    return _embed(texts, "RETRIEVAL_DOCUMENT") if texts else np.zeros((0, get_settings().gemini_embedding_dims), "float32")


# ------------------------------------------------------------- queries (memory + disk cache)

def _key(text: str) -> str:
    return hashlib.sha256(f"{model_id()}|{text}".encode()).hexdigest()


@lru_cache
def _disk_cache() -> dict[str, list[float]]:
    try:
        return json.loads(QUERY_CACHE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_cache() -> None:
    QUERY_CACHE.parent.mkdir(parents=True, exist_ok=True)
    tmp = QUERY_CACHE.with_suffix(".tmp")
    tmp.write_text(json.dumps(_disk_cache()), encoding="utf-8")
    tmp.replace(QUERY_CACHE)


def embed_query(text: str) -> np.ndarray:
    text = " ".join(text.split())
    key = _key(text)
    with _lock:
        cached = _disk_cache().get(key)
    if cached is not None:
        return normalise(np.asarray(cached, dtype="float32"))
    vec = _embed([text], "RETRIEVAL_QUERY")[0]
    with _lock:
        _disk_cache()[key] = [round(float(x), 7) for x in vec]
        _save_cache()
    return vec


def clear_query_cache(path: Path = QUERY_CACHE) -> None:
    _disk_cache.cache_clear()
    path.unlink(missing_ok=True)
