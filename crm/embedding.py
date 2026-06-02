"""Embedding backends for the novelty signal (§5.2, §5.3).

Default: `sentence-transformers/all-MiniLM-L6-v2` (per §5.2). If that model
cannot be loaded (no install / no network / offline CI), we fall back to a
DETERMINISTIC hashing embedder so tests run offline and fast. The fallback is
clearly labelled (`backend == "hash-fallback"`) so no reported result silently
relies on it — the real demo/ablations use the MiniLM backend.

The interface is a single `Embedder.encode(list[str]) -> np.ndarray` returning
L2-normalised row vectors, so cosine similarity is just a dot product.
"""

from __future__ import annotations

import hashlib

import numpy as np

DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def _normalise_rows(mat: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return mat / norms


class HashEmbedder:
    """Deterministic, dependency-free embedder (offline fallback).

    Hashes character 3-grams of the (normalised) statement into a fixed-width
    bag-of-features vector. It is NOT semantically strong, but it is stable,
    fast, and gives a meaningful *relative* distance: identical statements map
    to distance 0, edits move them apart. Used only when MiniLM is unavailable.
    """

    backend = "hash-fallback"
    dim = 256

    def _featurise(self, text: str) -> np.ndarray:
        t = "".join(text.lower().split())
        vec = np.zeros(self.dim, dtype=np.float64)
        if not t:
            return vec
        grams = [t[i:i + 3] for i in range(max(1, len(t) - 2))]
        for g in grams:
            h = int(hashlib.sha256(g.encode("utf-8")).hexdigest(), 16)
            vec[h % self.dim] += 1.0
        return vec

    def encode(self, texts: list[str]) -> np.ndarray:
        mat = np.vstack([self._featurise(t) for t in texts])
        return _normalise_rows(mat)


class STEmbedder:
    """sentence-transformers backend (default, §5.2)."""

    backend = "sentence-transformers"

    def __init__(self, model_name: str = DEFAULT_MODEL):
        from sentence_transformers import SentenceTransformer

        self.model_name = model_name
        self._model = SentenceTransformer(model_name)

    def encode(self, texts: list[str]) -> np.ndarray:
        emb = self._model.encode(
            list(texts), convert_to_numpy=True, normalize_embeddings=True
        )
        return np.asarray(emb, dtype=np.float64)


# Process-lifetime memo of constructed embedders, keyed by the resolved backend
# key (model name, or "hash" for the offline fallback). An Embedder instance is
# stateless across encode() calls (the MiniLM weights and the hash table are
# read-only), so reusing one instance for the whole process is side-effect-free
# and turns the per-arm "Loading weights" reload (arms x seeds reloads) into a
# single load. Caching is keyed so the hash backend and any distinct MiniLM
# model name each get their own cached instance.
_EMBEDDER_CACHE: dict[str, object] = {}


def get_embedder(model_name: str | None = DEFAULT_MODEL, allow_fallback: bool = True):
    """Return the configured embedder, falling back to HashEmbedder on failure.

    Pass `model_name=None` (or the special string "hash") to force the offline
    deterministic embedder explicitly (used by fast unit tests).

    The constructed embedder is memoised by backend key for the lifetime of the
    process, so repeated component builds (one per ablation/rounds-scaling arm)
    do NOT reload the SentenceTransformer weights every time.
    """
    def _hash() -> "HashEmbedder":
        # Lazily construct so the default is NOT built on every call (setdefault
        # would eagerly evaluate its default arg and defeat the cache).
        cached = _EMBEDDER_CACHE.get("hash")
        if cached is None:
            cached = HashEmbedder()
            _EMBEDDER_CACHE["hash"] = cached
        return cached

    if model_name in (None, "hash", "hash-fallback"):
        return _hash()
    cached = _EMBEDDER_CACHE.get(model_name)
    if cached is not None:
        return cached
    try:
        emb = STEmbedder(model_name)
    except Exception:
        if allow_fallback:
            # The MiniLM load failed; serve (and reuse) the hash fallback so a
            # later request for the same model does not re-attempt the load.
            return _hash()
        raise
    _EMBEDDER_CACHE[model_name] = emb
    return emb


def cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity of two (assumed L2-normalised) vectors."""
    return float(np.dot(a, b))
