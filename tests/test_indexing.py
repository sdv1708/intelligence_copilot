"""Indexing: the vector index and the chunk store must never disagree.

The single assertion this module exists for is
`test_re_chunking_never_returns_text_from_a_different_chunk`. Everything else
is scaffolding around it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.config import Settings
from core.db import Database
from core.exceptions import StorageError
from core.indexing import (
    check_index,
    delete_material_everywhere,
    ensure_meeting_indexed,
    index_material,
    open_index,
    rebuild_meeting_index,
    reindex_from_store,
)
from tests.fakes import HashingEmbedder

BUDGET = "The fourth quarter budget forecast shows revenue growth of twelve percent."
HIRING = "The hiring plan opens four engineering roles and two design roles."
LEGAL = "Legal review of the vendor contract renewal found two open items."


@pytest.fixture
def db(tmp_path: Path) -> Database:
    return Database(tmp_path / "test.db")


@pytest.fixture
def meeting_id(db: Database) -> str:
    return db.create_meeting("Quarterly Review", date="2026-07-28")


@pytest.fixture
def small(settings: Settings) -> Settings:
    """Chunks small enough that a paragraph of fixture text becomes several."""
    return settings.model_copy(update={"chunk_size": 80, "chunk_overlap": 20})


def add(db: Database, meeting_id: str, filename: str, text: str) -> str:
    return db.add_material(meeting_id, filename, "txt", text)


# --- Indexing one material --------------------------------------------------


def test_indexing_stores_chunks_and_vectors_under_the_same_ids(
    db: Database, meeting_id: str, small: Settings, embedder: HashingEmbedder
):
    material_id = add(db, meeting_id, "notes.txt", f"{BUDGET}\n\n{HIRING}\n\n{LEGAL}")

    chunk_ids = index_material(db, material_id, embedder=embedder, settings=small)

    assert chunk_ids
    assert [c.id for c in db.get_chunks_for_material(material_id)] == sorted(chunk_ids)
    assert open_index(meeting_id, small).ids() == set(chunk_ids)


def test_stored_chunks_still_slice_out_of_the_material(
    db: Database, meeting_id: str, small: Settings, embedder: HashingEmbedder
):
    """Offsets survive the round trip through SQLite."""
    text = f"{BUDGET}\n\n{HIRING}\n\n{LEGAL}"
    material_id = add(db, meeting_id, "notes.txt", text)

    index_material(db, material_id, embedder=embedder, settings=small)

    for chunk in db.get_chunks_for_material(material_id):
        assert text[chunk.char_start : chunk.char_end] == chunk.text


def test_re_indexing_replaces_rather_than_appends(
    db: Database, meeting_id: str, small: Settings, embedder: HashingEmbedder
):
    """Re-uploading a document used to add a second copy of it to the index."""
    material_id = add(db, meeting_id, "notes.txt", f"{BUDGET}\n\n{HIRING}")

    first = index_material(db, material_id, embedder=embedder, settings=small)
    second = index_material(db, material_id, embedder=embedder, settings=small)

    index = open_index(meeting_id, small)
    assert index.ntotal == len(second)
    assert index.ids() == set(second)
    assert not set(first) & set(second), "ids must not be recycled"


def test_indexing_an_unknown_material_is_refused(
    db: Database, small: Settings, embedder: HashingEmbedder
):
    with pytest.raises(StorageError, match="no material with id"):
        index_material(db, "material_nope", embedder=embedder, settings=small)


def test_an_empty_material_indexes_to_nothing(
    db: Database, meeting_id: str, small: Settings, embedder: HashingEmbedder
):
    material_id = add(db, meeting_id, "blank.txt", "   \n\n  ")

    assert index_material(db, material_id, embedder=embedder, settings=small) == []
    assert open_index(meeting_id, small).ntotal == 0


# --- The defect -------------------------------------------------------------


def test_re_chunking_never_returns_text_from_a_different_chunk(
    db: Database, meeting_id: str, small: Settings, embedder: HashingEmbedder
):
    """Store, index, delete, re-chunk, search — and check every id resolves true.

    This is the original defect written as an assertion. Ingestion and recall
    used different chunk boundaries and matched FAISS results to text by list
    position, so after any change to a meeting's materials a search returned a
    chunk of text that was not the one the vector had been built from. Nothing
    raised: the brief was simply about the wrong paragraph.

    Here the id is the contract. Whatever survives in the index must resolve to
    a live row whose text is exactly what was embedded under that id.
    """
    keep = add(db, meeting_id, "keep.txt", f"{BUDGET}\n\n{HIRING}\n\n{LEGAL}")
    doomed = add(db, meeting_id, "doomed.txt", f"{LEGAL}\n\n{BUDGET}\n\n{HIRING}")

    index_material(db, keep, embedder=embedder, settings=small)
    doomed_ids = index_material(db, doomed, embedder=embedder, settings=small)

    # A material disappears, and the surviving one is re-chunked with different
    # boundaries -- the exact sequence that used to desynchronise the index.
    delete_material_everywhere(db, doomed, settings=small)
    resized = small.model_copy(update={"chunk_size": 45, "chunk_overlap": 10})
    index_material(db, keep, embedder=embedder, settings=resized)

    index = open_index(meeting_id, small)
    assert not set(doomed_ids) & index.ids(), "deleted material's vectors remain"

    for query in (BUDGET, HIRING, LEGAL, "engineering roles", "vendor contract"):
        hits = index.search(embedder.encode([query]), k=10)
        for chunk_id, _ in hits:
            chunk = db.get_chunk(chunk_id)
            assert chunk is not None, f"vector {chunk_id} has no chunk row"
            assert chunk.material_id == keep
            # The row's text must be what was actually embedded under this id,
            # not merely some text from the same document.
            stored = db.get_material(keep).text
            assert stored[chunk.char_start : chunk.char_end] == chunk.text


def test_deleting_a_material_leaves_the_index_stale_but_detectably_so(
    db: Database, meeting_id: str, small: Settings, embedder: HashingEmbedder
):
    """Deletion cascades in SQL; the index file is only fixed on the next pass.

    That window is acceptable precisely because it is detectable: the ids are
    never reused, so the stale vectors point at nothing rather than at some
    other material's text.
    """
    material_id = add(db, meeting_id, "notes.txt", f"{BUDGET}\n\n{HIRING}")
    chunk_ids = index_material(db, material_id, embedder=embedder, settings=small)

    db.delete_material(material_id)

    health = check_index(db, meeting_id, settings=small)
    assert health.stored == 0
    assert health.orphaned == sorted(chunk_ids)
    assert not health.healthy

    reindex_from_store(db, meeting_id, embedder=embedder, settings=small)
    assert check_index(db, meeting_id, settings=small).healthy


def test_deleting_a_material_takes_its_vectors_with_it(
    db: Database, meeting_id: str, small: Settings, embedder: HashingEmbedder
):
    gone = add(db, meeting_id, "gone.txt", f"{BUDGET}\n\n{HIRING}")
    kept = add(db, meeting_id, "kept.txt", LEGAL)
    doomed = index_material(db, gone, embedder=embedder, settings=small)
    surviving = index_material(db, kept, embedder=embedder, settings=small)

    assert delete_material_everywhere(db, gone, settings=small)

    assert db.get_material(gone) is None
    assert open_index(meeting_id, small).ids() == set(surviving)
    assert not set(doomed) & open_index(meeting_id, small).ids()
    assert check_index(db, meeting_id, settings=small).healthy


def test_deleting_a_material_that_is_not_there_reports_so(
    db: Database, small: Settings
):
    assert delete_material_everywhere(db, "material_nope", settings=small) is False


# --- Meeting-level rebuilds -------------------------------------------------


def test_rebuilding_a_meeting_covers_every_material(
    db: Database, meeting_id: str, small: Settings, embedder: HashingEmbedder
):
    add(db, meeting_id, "one.txt", BUDGET)
    add(db, meeting_id, "two.txt", HIRING)

    report = rebuild_meeting_index(db, meeting_id, embedder=embedder, settings=small)

    assert report.materials == 2
    assert report.chunks == report.vectors == db.count_chunks(meeting_id)
    assert check_index(db, meeting_id, settings=small).healthy


def test_rebuilding_drops_vectors_of_materials_that_no_longer_exist(
    db: Database, meeting_id: str, small: Settings, embedder: HashingEmbedder
):
    gone = add(db, meeting_id, "gone.txt", BUDGET)
    kept = add(db, meeting_id, "kept.txt", HIRING)
    stale = index_material(db, gone, embedder=embedder, settings=small)
    index_material(db, kept, embedder=embedder, settings=small)

    db.delete_material(gone)
    rebuild_meeting_index(db, meeting_id, embedder=embedder, settings=small)

    assert not set(stale) & open_index(meeting_id, small).ids()


def test_reindexing_from_the_store_keeps_the_existing_ids(
    db: Database, meeting_id: str, small: Settings, embedder: HashingEmbedder
):
    """A missing index file must not invalidate chunk ids cited in old briefs."""
    material_id = add(db, meeting_id, "notes.txt", f"{BUDGET}\n\n{HIRING}")
    original = index_material(db, material_id, embedder=embedder, settings=small)

    small.index_path(meeting_id).unlink()
    reindex_from_store(db, meeting_id, embedder=embedder, settings=small)

    assert open_index(meeting_id, small).ids() == set(original)
    assert [c.id for c in db.get_chunks_for_material(material_id)] == sorted(original)


# --- Repair -----------------------------------------------------------------


def test_a_meeting_with_materials_but_no_chunks_is_chunked_on_demand(
    db: Database, meeting_id: str, small: Settings, embedder: HashingEmbedder
):
    """Meetings ingested before the chunk store existed still have to work."""
    add(db, meeting_id, "legacy.txt", f"{BUDGET}\n\n{HIRING}")

    report = ensure_meeting_indexed(db, meeting_id, embedder=embedder, settings=small)

    assert report is not None
    assert report.chunks > 0
    assert check_index(db, meeting_id, settings=small).healthy


def test_a_healthy_meeting_is_left_alone(
    db: Database, meeting_id: str, small: Settings, embedder: HashingEmbedder
):
    material_id = add(db, meeting_id, "notes.txt", BUDGET)
    index_material(db, material_id, embedder=embedder, settings=small)
    before = embedder.call_count

    assert ensure_meeting_indexed(db, meeting_id, embedder=embedder, settings=small) is None
    assert embedder.call_count == before, "a healthy index should not be re-embedded"


def test_a_meeting_with_no_materials_needs_no_repair(
    db: Database, meeting_id: str, small: Settings, embedder: HashingEmbedder
):
    assert ensure_meeting_indexed(db, meeting_id, embedder=embedder, settings=small) is None


def test_a_lost_index_file_is_rebuilt_on_demand(
    db: Database, meeting_id: str, small: Settings, embedder: HashingEmbedder
):
    material_id = add(db, meeting_id, "notes.txt", f"{BUDGET}\n\n{HIRING}")
    original = index_material(db, material_id, embedder=embedder, settings=small)
    small.index_path(meeting_id).unlink()

    report = ensure_meeting_indexed(db, meeting_id, embedder=embedder, settings=small)

    assert report is not None
    assert open_index(meeting_id, small).ids() == set(original)
