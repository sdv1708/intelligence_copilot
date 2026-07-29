"""Repository behaviour: constraints, cascades, and the chunk store's id contract."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.db import Database
from core.exceptions import IndexOutOfSyncError, MeetingNotFoundError, StorageError
from core.migrations import LATEST_VERSION
from core.schema import NewChunk


@pytest.fixture
def db(tmp_path: Path) -> Database:
    return Database(tmp_path / "test.db")


@pytest.fixture
def meeting_id(db: Database) -> str:
    return db.create_meeting("Weekly Sync", date="2026-07-28", attendees="Ada, Grace")


@pytest.fixture
def material_id(db: Database, meeting_id: str) -> str:
    return db.add_material(meeting_id, "notes.txt", "txt", "hello world" * 50)


def chunks(n: int, prefix: str = "chunk") -> list[NewChunk]:
    return [
        NewChunk(chunk_index=i, text=f"{prefix} {i}", char_start=i * 10, char_end=i * 10 + 8)
        for i in range(n)
    ]


# --- Setup and schema ------------------------------------------------------


def test_opening_a_database_migrates_it(db: Database):
    assert db.schema_version() == LATEST_VERSION


def test_creates_the_parent_directory(tmp_path: Path):
    nested = tmp_path / "a" / "b" / "briefs.db"
    Database(nested)
    assert nested.exists()


def test_reopening_preserves_data(tmp_path: Path):
    path = tmp_path / "test.db"
    first = Database(path)
    mid = first.create_meeting("Kickoff")

    reopened = Database(path)
    assert reopened.get_meeting(mid).title == "Kickoff"


def test_foreign_keys_are_enforced(db: Database):
    with db.connect() as conn:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_connection_rolls_back_on_error(db: Database, meeting_id: str):
    """A half-finished unit of work must not be left behind."""
    with pytest.raises(RuntimeError), db.connect() as conn:
        conn.execute("INSERT INTO meetings VALUES ('doomed','X',NULL,NULL,NULL,'t')")
        raise RuntimeError("boom")

    assert db.get_meeting("doomed") is None


# --- Meetings --------------------------------------------------------------


def test_create_and_read_a_meeting(db: Database):
    mid = db.create_meeting("Weekly Sync", date="2026-07-28", attendees="Ada, Grace")
    meeting = db.get_meeting(mid)

    assert meeting.id == mid
    assert meeting.title == "Weekly Sync"
    assert meeting.attendee_list == ["Ada", "Grace"]
    assert meeting.created_at


def test_get_missing_meeting_returns_none(db: Database):
    assert db.get_meeting("nope") is None


def test_require_meeting_raises_for_a_missing_id(db: Database):
    with pytest.raises(MeetingNotFoundError, match="nope"):
        db.require_meeting("nope")


def test_list_meetings_is_newest_first(db: Database):
    first = db.create_meeting("First")
    second = db.create_meeting("Second")
    third = db.create_meeting("Third")

    listed = [m.id for m in db.list_meetings()]
    assert listed == [third, second, first]


def test_delete_meeting_removes_everything_under_it(db: Database, meeting_id, material_id):
    db.replace_chunks(material_id, chunks(3))
    db.save_brief(meeting_id, "gemini", {"meeting_title": "Weekly Sync"})

    assert db.delete_meeting(meeting_id) is True
    assert db.get_meeting(meeting_id) is None
    assert db.get_materials(meeting_id) == []
    assert db.get_brief_history(meeting_id) == []
    assert db.count_chunks() == 0


def test_delete_missing_meeting_reports_false(db: Database):
    assert db.delete_meeting("nope") is False


# --- Materials -------------------------------------------------------------


def test_add_material_to_an_unknown_meeting_is_rejected(db: Database):
    """Previously accepted silently, producing a row nothing could reach."""
    with pytest.raises(MeetingNotFoundError):
        db.add_material("ghost_meeting", "notes.txt", "txt", "hello")


def test_get_materials_omits_the_text_but_reports_its_length(db: Database, meeting_id):
    db.add_material(meeting_id, "notes.txt", "txt", "x" * 1234)
    summary = db.get_materials(meeting_id)[0]

    assert summary.char_count == 1234
    assert summary.filename == "notes.txt"
    assert summary["meeting_id"] == meeting_id


def test_get_material_returns_the_full_text(db: Database, meeting_id):
    mid = db.add_material(meeting_id, "notes.txt", "txt", "the whole body")
    assert db.get_material(mid).text == "the whole body"


def test_get_material_missing_returns_none(db: Database):
    assert db.get_material("nope") is None


def test_delete_material(db: Database, meeting_id, material_id):
    assert db.delete_material(material_id) is True
    assert db.get_material(material_id) is None
    assert db.delete_material(material_id) is False


def test_iter_material_texts_is_oldest_first(db: Database, meeting_id):
    a = db.add_material(meeting_id, "a.txt", "txt", "aaa")
    b = db.add_material(meeting_id, "b.txt", "txt", "bbb")
    assert [m.id for m in db.iter_material_texts(meeting_id)] == [a, b]


# --- Chunks ----------------------------------------------------------------


def test_replace_chunks_returns_ids_in_order(db: Database, material_id):
    ids = db.replace_chunks(material_id, chunks(5))

    assert len(ids) == 5
    assert all(isinstance(i, int) and i > 0 for i in ids)
    assert ids == sorted(ids)


def test_stored_chunks_carry_the_meeting_id_from_their_material(
    db: Database, meeting_id, material_id
):
    db.replace_chunks(material_id, chunks(2))
    assert {c.meeting_id for c in db.get_chunks_for_material(material_id)} == {meeting_id}


def test_ids_map_back_to_exactly_the_text_that_was_stored(db: Database, material_id):
    """The whole point of the table: id -> text is a stable, one-to-one map."""
    ids = db.replace_chunks(material_id, chunks(6))

    for position, chunk_id in enumerate(ids):
        assert db.get_chunk(chunk_id).text == f"chunk {position}"


def test_replace_chunks_supersedes_the_previous_set(db: Database, material_id):
    old_ids = db.replace_chunks(material_id, chunks(4, prefix="old"))
    new_ids = db.replace_chunks(material_id, chunks(2, prefix="new"))

    assert db.count_chunks() == 2
    assert set(old_ids).isdisjoint(new_ids)
    assert [c.text for c in db.get_chunks_for_material(material_id)] == ["new 0", "new 1"]


def test_ids_are_never_reused_after_a_rechunk(db: Database, material_id):
    """A recycled id would point a live vector at unrelated text."""
    old_ids = db.replace_chunks(material_id, chunks(3))
    new_ids = db.replace_chunks(material_id, chunks(3))

    assert min(new_ids) > max(old_ids)


def test_stale_ids_resolve_to_nothing_rather_than_to_the_wrong_chunk(
    db: Database, material_id
):
    stale = db.replace_chunks(material_id, chunks(3, prefix="old"))
    db.replace_chunks(material_id, chunks(3, prefix="new"))

    assert db.get_chunk(stale[0]) is None


def test_replace_chunks_for_an_unknown_material_is_rejected(db: Database):
    with pytest.raises(StorageError, match="no material"):
        db.replace_chunks("ghost_material", chunks(1))


def test_replace_chunks_with_an_empty_list_clears_them(db: Database, material_id):
    db.replace_chunks(material_id, chunks(3))
    assert db.replace_chunks(material_id, []) == []
    assert db.count_chunks() == 0


def test_deleting_a_material_cascades_to_its_chunks(db: Database, meeting_id, material_id):
    """Requires PRAGMA foreign_keys = ON, which the old code never set."""
    other = db.add_material(meeting_id, "other.txt", "txt", "other body")
    db.replace_chunks(material_id, chunks(3))
    db.replace_chunks(other, chunks(2))

    db.delete_material(material_id)

    assert db.get_chunks_for_material(material_id) == []
    assert db.count_chunks() == 2


def test_get_chunks_by_ids_preserves_the_order_it_was_given(db: Database, material_id):
    """FAISS returns ids ranked by similarity; that ranking must survive."""
    ids = db.replace_chunks(material_id, chunks(5))
    requested = [ids[3], ids[0], ids[4]]

    assert [c.id for c in db.get_chunks_by_ids(requested)] == requested


def test_get_chunks_by_ids_skips_ids_that_are_gone(db: Database, material_id):
    ids = db.replace_chunks(material_id, chunks(3))
    result = db.get_chunks_by_ids([ids[0], 999_999, ids[2]])

    assert [c.id for c in result] == [ids[0], ids[2]]


def test_strict_lookup_raises_when_the_index_is_out_of_sync(db: Database, material_id):
    ids = db.replace_chunks(material_id, chunks(3))
    with pytest.raises(IndexOutOfSyncError, match="no longer exist"):
        db.get_chunks_by_ids([ids[0], 999_999], strict=True)


def test_get_chunks_by_ids_handles_more_ids_than_sqlite_allows_parameters(
    db: Database, material_id
):
    ids = db.replace_chunks(material_id, chunks(1200))
    assert len(db.get_chunks_by_ids(ids)) == 1200


def test_get_chunks_by_ids_of_nothing_is_empty(db: Database):
    assert db.get_chunks_by_ids([]) == []


def test_chunks_for_meeting_span_every_material(db: Database, meeting_id, material_id):
    other = db.add_material(meeting_id, "other.txt", "txt", "other body")
    db.replace_chunks(material_id, chunks(3))
    db.replace_chunks(other, chunks(2))

    assert len(db.get_chunks_for_meeting(meeting_id)) == 5
    assert db.count_chunks(meeting_id) == 5


def test_chunk_ids_for_meeting_are_sorted(db: Database, meeting_id, material_id):
    ids = db.replace_chunks(material_id, chunks(4))
    assert db.chunk_ids_for_meeting(meeting_id) == sorted(ids)


def test_neighbours_widen_around_a_hit(db: Database, material_id):
    ids = db.replace_chunks(material_id, chunks(5))
    neighbours = db.get_neighbour_chunks(ids[2], radius=1)

    assert [c.chunk_index for c in neighbours] == [1, 3]


def test_neighbours_do_not_run_past_the_start_of_a_material(db: Database, material_id):
    ids = db.replace_chunks(material_id, chunks(5))
    assert [c.chunk_index for c in db.get_neighbour_chunks(ids[0], radius=2)] == [1, 2]


def test_neighbours_never_cross_into_another_material(db: Database, meeting_id, material_id):
    """Adjacency is by chunk_index within a material, not by row id."""
    other = db.add_material(meeting_id, "other.txt", "txt", "other body")
    ids = db.replace_chunks(material_id, chunks(3, prefix="first"))
    db.replace_chunks(other, chunks(3, prefix="second"))

    neighbours = db.get_neighbour_chunks(ids[2], radius=2)
    assert all(c.material_id == material_id for c in neighbours)


def test_zero_radius_returns_no_neighbours(db: Database, material_id):
    ids = db.replace_chunks(material_id, chunks(3))
    assert db.get_neighbour_chunks(ids[1], radius=0) == []


def test_neighbours_of_a_missing_chunk_are_empty(db: Database):
    assert db.get_neighbour_chunks(999_999) == []


def test_delete_chunks_for_material_leaves_the_material(db: Database, material_id):
    db.replace_chunks(material_id, chunks(3))
    assert db.delete_chunks_for_material(material_id) == 3
    assert db.get_material(material_id) is not None
    assert db.count_chunks() == 0


def test_a_material_cannot_hold_two_chunks_at_the_same_index(db: Database, material_id):
    import sqlite3

    with pytest.raises(sqlite3.IntegrityError):
        db.replace_chunks(
            material_id,
            [
                NewChunk(chunk_index=0, text="a"),
                NewChunk(chunk_index=0, text="b"),
            ],
        )


# --- Briefs ----------------------------------------------------------------


def test_save_and_reload_a_brief(db: Database, meeting_id):
    payload = {"meeting_title": "Weekly Sync", "key_topics_today": ["Hiring"]}
    brief_id = db.save_brief(meeting_id, "gemini", payload)

    record = db.get_brief_by_id(brief_id)
    assert record.model == "gemini"
    assert record["brief"] == payload
    assert record.as_brief().key_topics_today == ["Hiring"]


def test_save_brief_for_an_unknown_meeting_is_rejected(db: Database):
    with pytest.raises(MeetingNotFoundError):
        db.save_brief("ghost_meeting", "gemini", {"meeting_title": "X"})


def test_latest_brief_is_the_most_recent(db: Database, meeting_id):
    db.save_brief(meeting_id, "gemini", {"meeting_title": "first"})
    db.save_brief(meeting_id, "gemini", {"meeting_title": "second"})
    newest = db.save_brief(meeting_id, "openai", {"meeting_title": "third"})

    latest = db.get_latest_brief(meeting_id)
    assert latest.id == newest
    assert latest.brief["meeting_title"] == "third"


def test_latest_brief_when_there_are_none(db: Database, meeting_id):
    assert db.get_latest_brief(meeting_id) is None


def test_brief_history_is_newest_first_and_omits_payloads(db: Database, meeting_id):
    db.save_brief(meeting_id, "gemini", {"meeting_title": "first"})
    second = db.save_brief(meeting_id, "gemini", {"meeting_title": "second"})

    history = db.get_brief_history(meeting_id)
    assert history[0].id == second
    assert len(history) == 2
    assert "brief" not in history[0]


def test_brief_with_unreadable_json_degrades_instead_of_crashing(db: Database, meeting_id):
    """One corrupted row must not take the whole history list down."""
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO briefs VALUES ('b_corrupt', ?, '2026-07-28T00:00:00+00:00', "
            "'gemini', 'not json at all')",
            (meeting_id,),
        )

    record = db.get_brief_by_id("b_corrupt")
    assert record is not None
    assert record.brief == {}


def test_brief_payload_keeps_non_ascii_intact(db: Database, meeting_id):
    brief_id = db.save_brief(meeting_id, "gemini", {"meeting_title": "Café — año"})
    assert db.get_brief_by_id(brief_id).brief["meeting_title"] == "Café — año"


def test_get_brief_by_id_missing_returns_none(db: Database):
    assert db.get_brief_by_id("nope") is None
