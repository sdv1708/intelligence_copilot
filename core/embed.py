"""Embeddings and the vector index, keyed on chunk row ids.

The substantive change here is `VectorIndex`. The previous implementation used
a bare `faiss.IndexFlatIP`, which numbers its vectors 0, 1, 2, ... in insertion
order and knows nothing else about them. Callers recovered the text for a hit
by re-chunking the material at query time and indexing a Python list with the
FAISS position — a correspondence that held only while nothing was ever added,
removed, re-ingested or re-chunked, and that failed silently the moment
anything was.

`faiss.IndexIDMap2` stores an explicit int64 alongside each vector. That id is
the `chunks.id` primary key, so a search result names exactly one database row.
When a material is re-chunked its old ids are removed from the index and its
new rows get new ids (the table is `AUTOINCREMENT`, so ids are never reused).
The failure mode therefore changes from "returns the wrong text" to "the id is
absent from the store", which `Database.get_chunks_by_ids(strict=True)` raises
on. A loud, locatable inconsistency instead of a quiet, plausible one.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

import numpy as np

from core.config import Settings, get_settings
from core.exceptions import RetrievalError
from core.logging_config import get_logger

if TYPE_CHECKING:  # pragma: no cover - import cost is the point
    import faiss

logger = get_logger(__name__)


# --- Embedders --------------------------------------------------------------


@runtime_checkable
class Embedder(Protocol):
    """Anything that turns texts into L2-normalised row vectors.

    Kept as a protocol so retrieval and indexing can be exercised with
    `tests.fakes.HashingEmbedder`, which is lexical and deterministic, without
    downloading 90MB of model weights to assert that a search returns rows in
    the right order.
    """

    dim: int

    def encode(self, texts: Sequence[str]) -> np.ndarray: ...


class SentenceTransformerEmbedder:
    """The real encoder: `all-MiniLM-L6-v2` by default, GPU when available.

    Model loading is deferred to the first `encode` call. Constructing one of
    these should not cost several seconds and a gigabyte of RAM if nothing ends
    up being embedded — `api/deps.py` warms it deliberately at startup instead,
    so the cost lands before the first request rather than inside it.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self.dim = self._settings.embedding_dim
        self._model = None
        self._device: str | None = None

    @property
    def device(self) -> str:
        if self._device is None:
            configured = self._settings.embedding_device
            if configured != "auto":
                self._device = configured
            else:
                self._device = _detect_device()
            logger.info("Embedding device: %s", self._device)
        return self._device

    @property
    def model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            name = self._settings.embedding_model
            logger.info("Loading embedding model %s on %s", name, self.device)
            self._model = SentenceTransformer(name, device=self.device)

            actual = int(self._model.get_sentence_embedding_dimension())
            if actual != self.dim:
                # Silently embedding into a different dimension than the index
                # was built for produces an unreadable index, so fail here.
                raise RetrievalError(
                    f"Embedding model {name} produces {actual}-dimensional vectors "
                    f"but embedding_dim is configured as {self.dim}. Set "
                    f"EMBEDDING_DIM={actual} or choose a different model."
                )
        return self._model

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        texts = list(texts)
        if not texts:
            return np.zeros((0, self.dim), dtype="float32")

        batch_size = self._settings.embedding_batch_size or (
            64 if self.device == "cuda" else 16
        )
        vectors = self.model.encode(
            texts,
            normalize_embeddings=True,
            batch_size=batch_size,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return np.ascontiguousarray(vectors, dtype="float32")


def _detect_device() -> str:
    try:
        import torch
    except ImportError:  # pragma: no cover - torch ships with the embedder
        return "cpu"
    if torch.cuda.is_available():
        logger.info("GPU detected: %s", torch.cuda.get_device_name(0))
        return "cuda"
    return "cpu"


_embedder: SentenceTransformerEmbedder | None = None


def get_embedder(settings: Settings | None = None) -> SentenceTransformerEmbedder:
    """Process-wide embedder. One model load per process, not per request."""
    global _embedder
    if _embedder is None:
        _embedder = SentenceTransformerEmbedder(settings)
    return _embedder


def reset_embedder_cache() -> None:
    """Drop the cached embedder. Used by tests and after a settings change."""
    global _embedder
    _embedder = None


def encode(texts: Sequence[str]) -> np.ndarray:
    """Encode with the process-wide embedder."""
    return get_embedder().encode(texts)


def get_model():
    """The underlying SentenceTransformer. Used by the app's model preloader."""
    return get_embedder().model


def get_device() -> str:
    """The device the embedder will run on."""
    return get_embedder().device


# --- Vector index -----------------------------------------------------------


class VectorIndex:
    """A meeting's FAISS index, addressed by chunk row id.

    Inner product over L2-normalised vectors, so a score is cosine similarity
    in `[-1, 1]` and can be compared against `settings.min_similarity`
    meaningfully.
    """

    def __init__(self, path: Path | str, dim: int, index: faiss.Index | None = None):
        self.path = Path(path)
        self.dim = dim
        self._index = index if index is not None else _new_index(dim)

    # --- Construction ---

    @classmethod
    def open(cls, path: Path | str, dim: int) -> VectorIndex:
        """Load the index at `path`, or start an empty one.

        An existing file that is not id-mapped, or is the wrong dimension, is
        discarded rather than adapted. Those files come from the pre-overhaul
        code, where positions were the only identifiers; there is no
        information in them that could be recovered into ids, so rebuilding
        from the chunk store is the only correct move.
        """
        import faiss

        path = Path(path)
        if not path.exists():
            return cls(path, dim)

        try:
            loaded = faiss.read_index(str(path))
        except Exception as exc:
            logger.warning("Could not read index %s (%s); starting empty", path, exc)
            return cls(path, dim)

        if not isinstance(loaded, faiss.IndexIDMap | faiss.IndexIDMap2):
            logger.warning(
                "Index %s stores no vector ids (%s). It predates id-keyed "
                "retrieval and cannot be mapped back to chunks; rebuilding.",
                path,
                type(loaded).__name__,
            )
            return cls(path, dim)

        if loaded.d != dim:
            logger.warning(
                "Index %s has dimension %d but %d is configured; rebuilding.",
                path,
                loaded.d,
                dim,
            )
            return cls(path, dim)

        return cls(path, dim, loaded)

    # --- Inspection ---

    @property
    def ntotal(self) -> int:
        return int(self._index.ntotal)

    def ids(self) -> set[int]:
        """Every vector id currently in the index."""
        import faiss

        if self.ntotal == 0:
            return set()
        return set(faiss.vector_to_array(self._index.id_map).tolist())

    def __contains__(self, chunk_id: int) -> bool:
        return chunk_id in self.ids()

    # --- Mutation ---

    def add(self, chunk_ids: Sequence[int], vectors: np.ndarray) -> int:
        """Add `vectors` under `chunk_ids`. Returns how many were added."""
        if len(chunk_ids) != len(vectors):
            raise RetrievalError(
                f"Cannot index {len(vectors)} vectors under {len(chunk_ids)} ids; "
                "every vector must have exactly one chunk id."
            )
        if not chunk_ids:
            return 0

        vectors = _as_matrix(vectors, self.dim)
        self._index.add_with_ids(vectors, np.asarray(chunk_ids, dtype="int64"))
        return len(chunk_ids)

    def remove(self, chunk_ids: Sequence[int]) -> int:
        """Remove vectors by chunk id. Returns how many were actually removed."""
        if not chunk_ids or self.ntotal == 0:
            return 0
        removed = self._index.remove_ids(np.asarray(chunk_ids, dtype="int64"))
        return int(removed)

    def reset(self) -> None:
        """Empty the index in place, keeping its path."""
        self._index = _new_index(self.dim)

    # --- Query ---

    def search(self, query: np.ndarray, k: int) -> list[tuple[int, float]]:
        """Return up to `k` `(chunk_id, score)` pairs, best first.

        FAISS pads a short result set with an id of `-1`; those are dropped
        here so callers never see a sentinel masquerading as a row id.
        """
        if self.ntotal == 0 or k <= 0:
            return []

        query = _as_matrix(query, self.dim)
        if len(query) != 1:
            raise RetrievalError(
                f"search expects a single query vector, got {len(query)}."
            )

        scores, ids = self._index.search(query, min(k, self.ntotal))
        return [
            (int(chunk_id), float(score))
            for chunk_id, score in zip(ids[0], scores[0], strict=True)
            if chunk_id != -1
        ]

    # --- Persistence ---

    def save(self) -> Path:
        import faiss

        self.path.parent.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self._index, str(self.path))
        logger.debug("Wrote index %s (%d vectors)", self.path, self.ntotal)
        return self.path

    def delete_file(self) -> bool:
        """Remove the on-disk index. Returns whether a file was there."""
        if self.path.exists():
            self.path.unlink()
            return True
        return False


def _new_index(dim: int) -> faiss.Index:
    import faiss

    return faiss.IndexIDMap2(faiss.IndexFlatIP(dim))


def _as_matrix(vectors: np.ndarray, dim: int) -> np.ndarray:
    """Coerce to a contiguous float32 `(n, dim)` array, or explain why not."""
    array = np.asarray(vectors, dtype="float32")
    if array.ndim == 1:
        array = array.reshape(1, -1)
    if array.ndim != 2 or array.shape[1] != dim:
        raise RetrievalError(
            f"Expected vectors shaped (n, {dim}), got {array.shape}. The "
            "embedding model and the index disagree about dimensionality."
        )
    return np.ascontiguousarray(array)
