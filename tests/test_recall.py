"""Retrieval: relevance ordering, neighbour expansion, and honest failure.

`HashingEmbedder` is lexical, so these tests can assert that a query really
does rank the chunk that shares its words first, rather than only checking that
the plumbing returns the right number of objects.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.config import Settings
from core.db import Database
from core.exceptions import IndexOutOfSyncError
from core.indexing import index_material, open_index
from core.recall import Retriever, format_context_blocks, recall_context
from core.schema import Chunk, ScoredChunk
from tests.fakes import HashingEmbedder

BUDGET = (
    "The fourth quarter budget forecast projects revenue growth of twelve "
    "percent against a flat cost base."
)
HIRING = (
    "The hiring plan opens four engineering roles and two design roles, with "
    "offers going out in September."
)
LEGAL = (
    "Legal review of the vendor contract renewal surfaced two open indemnity "
    "clauses that need signature."
)
LOGISTICS = (
    "Catering for the offsite is booked and the shuttle timetable has been "
    "circulated to everyone attending."
)


@pytest.fixture
def db(tmp_path: Path) -> Database:
    return Database(tmp_path / "test.db")


@pytest.fixture
def small(settings: Settings) -> Settings:
    """Small chunks and a permissive floor, so each paragraph is its own chunk."""
    return settings.model_copy(
        update={"chunk_size": 140, "chunk_overlap": 20, "min_similarity": 0.0}
    )


@pytest.fixture
def meeting_id(db: Database, small: Settings, embedder: HashingEmbedder) -> str:
    """A meeting with one material of four clearly distinct paragraphs."""
    meeting_id = db.create_meeting("Quarterly Review", date="2026-07-28")
    material_id = db.add_material(
        meeting_id,
        "notes.txt",
        "txt",
        "\n\n".join([BUDGET, HIRING, LEGAL, LOGISTICS]),
    )
    index_material(db, material_id, embedder=embedder, settings=small)
    return meeting_id


@pytest.fixture
def retriever(db: Database, small: Settings, embedder: HashingEmbedder) -> Retriever:
    return Retriever(db, embedder=embedder, settings=small)


def texts(results: list[ScoredChunk]) -> list[str]:
    return [scored.chunk.text for scored in results]


def hits(results: list[ScoredChunk]) -> list[ScoredChunk]:
    return [scored for scored in results if not scored.is_neighbour]


# --- Relevance --------------------------------------------------------------


def test_the_best_match_is_the_chunk_that_shares_the_query_words(
    retriever: Retriever, meeting_id: str
):
    results = retriever.recall(meeting_id, "indemnity clauses in the vendor contract", k=1)

    assert "indemnity" in hits(results)[0].chunk.text


def test_results_are_ordered_by_score(retriever: Retriever, meeting_id: str):
    results = hits(retriever.recall(meeting_id, "engineering and design roles", k=4))

    scores = [scored.score for scored in results]
    assert scores == sorted(scores, reverse=True)
    assert "hiring plan" in results[0].chunk.text


def test_k_bounds_the_number_of_hits(retriever: Retriever, meeting_id: str):
    results = retriever.recall(meeting_id, "budget revenue", k=2, neighbour_radius=0)

    assert len(results) == 2


def test_recalled_text_is_the_text_that_was_indexed(
    retriever: Retriever, db: Database, meeting_id: str
):
    """The id contract, checked from the retrieval side."""
    results = retriever.recall(meeting_id, "shuttle timetable for the offsite", k=3)

    for scored in results:
        material = db.get_material(scored.chunk.material_id)
        assert material.text[scored.chunk.char_start : scored.chunk.char_end] == (
            scored.chunk.text
        )


def test_the_similarity_floor_discards_weak_matches(
    db: Database, small: Settings, embedder: HashingEmbedder, meeting_id: str
):
    retriever = Retriever(db, embedder=embedder, settings=small)

    results = retriever.recall(
        meeting_id, "quantum chromodynamics lattice gauge", k=4, min_similarity=0.9
    )

    assert results == []


# --- Neighbour expansion ----------------------------------------------------


def test_neighbours_are_pulled_in_around_a_hit(retriever: Retriever, meeting_id: str):
    """Small chunks retrieve precisely; neighbours give the model the context back."""
    results = retriever.recall(meeting_id, "indemnity clauses", k=1, neighbour_radius=1)

    assert len(results) > 1
    assert [scored.is_neighbour for scored in results].count(False) == 1
    assert any("hiring plan" in text for text in texts(results))


def test_neighbours_are_flagged_and_keep_document_order(
    retriever: Retriever, meeting_id: str
):
    results = retriever.recall(meeting_id, "indemnity clauses", k=1, neighbour_radius=1)

    indices = [scored.chunk.chunk_index for scored in results]
    assert indices == sorted(indices)
    assert all(isinstance(scored.chunk, Chunk) for scored in results)


def test_a_chunk_is_never_returned_twice(retriever: Retriever, meeting_id: str):
    results = retriever.recall(meeting_id, "budget hiring legal offsite", k=4, neighbour_radius=2)

    ids = [scored.chunk.id for scored in results]
    assert len(ids) == len(set(ids))


def test_a_hit_is_not_downgraded_to_a_neighbour(retriever: Retriever, meeting_id: str):
    """Overlapping expansions must not relabel a real match as filler."""
    results = retriever.recall(meeting_id, "budget hiring legal offsite", k=4, neighbour_radius=2)

    assert len(hits(results)) == 4


def test_radius_zero_returns_hits_only(retriever: Retriever, meeting_id: str):
    results = retriever.recall(meeting_id, "vendor contract", k=2, neighbour_radius=0)

    assert all(not scored.is_neighbour for scored in results)


def test_neighbours_never_cross_a_material_boundary(
    db: Database, small: Settings, embedder: HashingEmbedder
):
    """Adjacency is by chunk_index within a material, not by row id arithmetic.

    Two materials indexed back to back have consecutive row ids, so expanding
    by id would reach straight into the next document.
    """
    meeting_id = db.create_meeting("Two Documents")
    first = db.add_material(meeting_id, "one.txt", "txt", f"{BUDGET}\n\n{HIRING}")
    second = db.add_material(meeting_id, "two.txt", "txt", f"{LEGAL}\n\n{LOGISTICS}")
    index_material(db, first, embedder=embedder, settings=small)
    index_material(db, second, embedder=embedder, settings=small)

    results = Retriever(db, embedder=embedder, settings=small).recall(
        meeting_id, "engineering roles offers", k=1, neighbour_radius=3
    )

    assert {scored.chunk.material_id for scored in results} == {first}


# --- Queryless recall -------------------------------------------------------


def test_an_empty_query_returns_the_whole_of_a_small_meeting(
    retriever: Retriever, db: Database, meeting_id: str
):
    results = retriever.recall(meeting_id, "", k=8)

    assert len(results) == db.count_chunks(meeting_id)


def test_an_empty_query_samples_across_a_large_meeting(
    db: Database, small: Settings, embedder: HashingEmbedder
):
    """A sweep must span the document, not stop after its first page.

    Taking the first k chunks would brief the model on the opening section and
    nothing else.
    """
    meeting_id = db.create_meeting("Long Document")
    paragraphs = [f"Section {n} discusses topic number {n} in some detail." for n in range(60)]
    material_id = db.add_material(meeting_id, "long.txt", "txt", "\n\n".join(paragraphs))
    index_material(db, material_id, embedder=embedder, settings=small)

    results = Retriever(db, embedder=embedder, settings=small).recall(
        meeting_id, "", k=6, neighbour_radius=0
    )

    positions = [scored.chunk.chunk_index for scored in results]
    total = db.count_chunks(meeting_id)
    assert len(results) < total
    assert max(positions) > total * 0.6, "the sweep never reached the end of the document"


def test_an_empty_query_covers_every_material(
    db: Database, small: Settings, embedder: HashingEmbedder
):
    meeting_id = db.create_meeting("Two Documents")
    for name, body in (("one.txt", BUDGET), ("two.txt", LEGAL)):
        material_id = db.add_material(meeting_id, name, "txt", body)
        index_material(db, material_id, embedder=embedder, settings=small)

    results = Retriever(db, embedder=embedder, settings=small).recall(meeting_id, "", k=2)

    assert len({scored.chunk.material_id for scored in results}) == 2


# --- Empty and broken states ------------------------------------------------


def test_a_meeting_with_no_materials_recalls_nothing(
    db: Database, retriever: Retriever
):
    empty = db.create_meeting("Nothing Here")

    assert retriever.recall(empty, "anything at all") == []
    assert retriever.recall(empty, "") == []


def test_an_index_pointing_at_deleted_chunks_raises(
    db: Database, small: Settings, embedder: HashingEmbedder, meeting_id: str
):
    """The failure the old code hid: rather than return the wrong text, say so.

    Auto-repair is off here so the broken state survives long enough to assert
    on; with it on, `ensure_meeting_indexed` fixes this before the search.
    """
    with db.connect() as conn:
        conn.execute("DELETE FROM chunks WHERE meeting_id = ?", (meeting_id,))

    retriever = Retriever(db, embedder=embedder, settings=small, auto_repair=False)

    with pytest.raises(IndexOutOfSyncError):
        retriever.recall(meeting_id, "budget forecast", k=2)


def test_retrieval_repairs_a_meeting_that_was_never_chunked(
    db: Database, small: Settings, embedder: HashingEmbedder
):
    """Pre-overhaul meetings have materials and no chunks; search must still work."""
    meeting_id = db.create_meeting("Legacy Meeting")
    db.add_material(meeting_id, "old.txt", "txt", f"{BUDGET}\n\n{LEGAL}")

    results = Retriever(db, embedder=embedder, settings=small).recall(
        meeting_id, "revenue growth forecast", k=1
    )

    assert results
    assert db.count_chunks(meeting_id) > 0
    assert open_index(meeting_id, small).ntotal > 0


# --- Formatting -------------------------------------------------------------


def test_context_blocks_cite_a_resolvable_source(
    retriever: Retriever, meeting_id: str
):
    results = retriever.recall(meeting_id, "vendor contract renewal", k=1)

    blocks = format_context_blocks(results)

    assert f"Source: {results[0].chunk.source_ref}" in blocks
    assert results[0].chunk.text in blocks


def test_context_blocks_mark_neighbours_as_context(
    retriever: Retriever, meeting_id: str
):
    """The model must not be told a filler chunk was a strong match."""
    results = retriever.recall(meeting_id, "indemnity clauses", k=1, neighbour_radius=1)

    blocks = format_context_blocks(results)

    assert "(surrounding context)" in blocks
    assert blocks.count("Source:") == len(results)


def test_context_blocks_label_materials_by_filename(
    retriever: Retriever, meeting_id: str
):
    results = retriever.recall(meeting_id, "budget forecast", k=1)

    blocks = retriever.format_context(results, meeting_id)

    assert "=== Material: notes.txt" in blocks


def test_empty_results_format_to_a_statement_not_an_empty_string():
    assert format_context_blocks([]) == "No context retrieved."


# --- The transitional shim --------------------------------------------------


def test_recall_context_accepts_a_raw_connection(
    db: Database, meeting_id: str, monkeypatch: pytest.MonkeyPatch, small: Settings
):
    """The orchestrator still passes `db.get_connection()` until Chunk 6."""
    monkeypatch.setattr("core.recall.get_settings", lambda: small)
    monkeypatch.setattr("core.recall.get_embedder", lambda _: HashingEmbedder())

    conn = db.get_connection()
    try:
        results = recall_context(conn, meeting_id, query="budget forecast", k=2)
    finally:
        conn.close()

    assert results
    assert all(isinstance(scored, ScoredChunk) for scored in results)


def test_recall_context_accepts_a_repository(
    db: Database, meeting_id: str, monkeypatch: pytest.MonkeyPatch, small: Settings
):
    monkeypatch.setattr("core.recall.get_settings", lambda: small)
    monkeypatch.setattr("core.recall.get_embedder", lambda _: HashingEmbedder())

    assert recall_context(db, meeting_id, query="hiring plan", k=1)
