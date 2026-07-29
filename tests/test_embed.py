"""The vector index: ids in, the same ids back out."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from core.embed import VectorIndex, _as_matrix
from core.exceptions import RetrievalError
from tests.fakes import HashingEmbedder

DIM = 384


@pytest.fixture
def index(tmp_path: Path) -> VectorIndex:
    return VectorIndex(tmp_path / "meeting.faiss", DIM)


@pytest.fixture
def vectors(embedder: HashingEmbedder) -> np.ndarray:
    return embedder.encode(
        [
            "the budget forecast for the fourth quarter",
            "hiring plan and open engineering roles",
            "vendor contract renewal and legal review",
        ]
    )


def test_search_returns_the_ids_it_was_given(index: VectorIndex, vectors, embedder):
    index.add([1001, 1002, 1003], vectors)

    hits = index.search(embedder.encode(["fourth quarter budget forecast"]), k=3)

    assert hits[0][0] == 1001
    assert {chunk_id for chunk_id, _ in hits} == {1001, 1002, 1003}


def test_ids_need_not_be_contiguous_or_start_at_zero(index: VectorIndex, vectors, embedder):
    """Chunk row ids are arbitrary int64s; positional indices were the old bug."""
    index.add([70001, 4, 999999999], vectors)

    hits = index.search(embedder.encode(["legal review of the vendor contract"]), k=1)

    assert hits[0][0] == 999999999


def test_scores_are_cosine_similarities(index: VectorIndex, vectors, embedder):
    index.add([1, 2, 3], vectors)

    hits = index.search(vectors[:1], k=3)

    assert hits[0][1] == pytest.approx(1.0, abs=1e-5)
    assert all(-1.0 <= score <= 1.0 for _, score in hits)


def test_removed_ids_stop_being_returned(index: VectorIndex, vectors, embedder):
    index.add([1, 2, 3], vectors)

    assert index.remove([2]) == 1

    hits = index.search(embedder.encode(["hiring plan open roles"]), k=3)
    assert 2 not in {chunk_id for chunk_id, _ in hits}
    assert index.ntotal == 2


def test_a_short_index_does_not_pad_results_with_minus_one(index: VectorIndex, vectors):
    """FAISS returns -1 for empty slots; those must never reach a caller."""
    index.add([5], vectors[:1])

    hits = index.search(vectors[:1], k=10)

    assert len(hits) == 1
    assert hits[0][0] == 5


def test_searching_an_empty_index_returns_nothing(index: VectorIndex, vectors):
    assert index.search(vectors[:1], k=5) == []


def test_ids_are_reported(index: VectorIndex, vectors):
    index.add([11, 22, 33], vectors)

    assert index.ids() == {11, 22, 33}
    assert 22 in index
    assert 44 not in index


def test_round_trips_through_disk(tmp_path: Path, vectors, embedder):
    path = tmp_path / "meeting.faiss"
    written = VectorIndex(path, DIM)
    written.add([101, 202, 303], vectors)
    written.save()

    reopened = VectorIndex.open(path, DIM)

    assert reopened.ntotal == 3
    assert reopened.ids() == {101, 202, 303}
    assert reopened.search(vectors[:1], k=1)[0][0] == 101


def test_opening_a_missing_file_starts_empty(tmp_path: Path):
    assert VectorIndex.open(tmp_path / "absent.faiss", DIM).ntotal == 0


def test_a_pre_overhaul_index_without_ids_is_discarded(tmp_path: Path, vectors):
    """The old files store positions, not ids. There is nothing to migrate.

    Adapting one would mean guessing which chunk each position meant, which is
    the guess that produced mismatched text in the first place.
    """
    import faiss

    path = tmp_path / "legacy.faiss"
    legacy = faiss.IndexFlatIP(DIM)
    legacy.add(vectors)
    faiss.write_index(legacy, str(path))

    reopened = VectorIndex.open(path, DIM)

    assert reopened.ntotal == 0


def test_an_index_of_the_wrong_dimension_is_discarded(tmp_path: Path):
    import faiss

    path = tmp_path / "small.faiss"
    faiss.write_index(faiss.IndexIDMap2(faiss.IndexFlatIP(8)), str(path))

    assert VectorIndex.open(path, DIM).ntotal == 0


def test_an_unreadable_file_does_not_crash_startup(tmp_path: Path):
    path = tmp_path / "corrupt.faiss"
    path.write_bytes(b"not a faiss index")

    assert VectorIndex.open(path, DIM).ntotal == 0


def test_adding_mismatched_ids_and_vectors_is_refused(index: VectorIndex, vectors):
    with pytest.raises(RetrievalError, match="every vector must have exactly one"):
        index.add([1, 2], vectors)


def test_vectors_of_the_wrong_width_are_refused(index: VectorIndex):
    with pytest.raises(RetrievalError, match="disagree about dimensionality"):
        index.add([1], np.zeros((1, 8), dtype="float32"))


def test_reset_empties_the_index(index: VectorIndex, vectors):
    index.add([1, 2, 3], vectors)
    index.reset()

    assert index.ntotal == 0
    assert index.ids() == set()


def test_a_single_query_vector_may_be_one_dimensional(index: VectorIndex, vectors):
    index.add([9], vectors[:1])

    assert index.search(vectors[0], k=1)[0][0] == 9


def test_matrix_coercion_rejects_a_batch_of_queries(index: VectorIndex, vectors):
    index.add([1, 2, 3], vectors)

    with pytest.raises(RetrievalError, match="single query vector"):
        index.search(vectors, k=1)


def test_as_matrix_produces_contiguous_float32():
    coerced = _as_matrix(np.ones((2, DIM), dtype="float64"), DIM)

    assert coerced.dtype == np.float32
    assert coerced.flags["C_CONTIGUOUS"]
