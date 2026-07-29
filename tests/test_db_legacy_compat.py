"""Guards for the two things Chunk 2 must not break.

1. `app.py` and `agents/copilot_orchestrator.py` have not been rewritten yet.
   They index repository results like dicts and pass raw connections around.
   Those access patterns are pinned here so the data layer can keep changing
   underneath them until Chunks 6-8 replace them.
2. A database written by the pre-migration code must be adopted in place, with
   every row intact. This is the `data/briefs.db` scenario in miniature.

Both files are expected to be deleted with the code they protect.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from core.db import Database
from core.migrations import LATEST_VERSION
from core.schema import MeetingBrief

LEGACY_BRIEF = {
    "meeting_title": "Q4 Planning",
    "time_window": "2025-11-10..2025-11-11",
    "last_meeting_recap": "We agreed to ship the beta.",
    "open_action_items": [
        {"owner": "Ada", "item": "Draft the rollout plan", "due": "2025-11-15", "status": "open"}
    ],
    "key_topics_today": ["Rollout", "Hiring"],
    "proposed_agenda": [{"topic": "Rollout", "minutes": 20, "owner": "Ada"}],
    "evidence": [{"source": "material_abc#c3", "snippet": "the beta ships Friday"}],
}


@pytest.fixture
def legacy_db_path(tmp_path: Path) -> Path:
    """A database in exactly the shape the pre-overhaul code produced."""
    path = tmp_path / "briefs.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE meetings (
            id TEXT PRIMARY KEY, title TEXT NOT NULL, date TEXT,
            attendees TEXT, tags TEXT, created_at TEXT NOT NULL
        );
        CREATE TABLE materials (
            id TEXT PRIMARY KEY, meeting_id TEXT NOT NULL, filename TEXT,
            media_type TEXT, text TEXT, created_at TEXT NOT NULL,
            FOREIGN KEY (meeting_id) REFERENCES meetings(id)
        );
        CREATE TABLE briefs (
            id TEXT PRIMARY KEY, meeting_id TEXT NOT NULL, created_at TEXT NOT NULL,
            model TEXT, brief_json TEXT NOT NULL,
            FOREIGN KEY (meeting_id) REFERENCES meetings(id)
        );
        """
    )
    conn.execute(
        "INSERT INTO meetings VALUES ('meeting_1','AI engineering','2025-11-11',"
        "'a,b,c',NULL,'2025-11-11T15:20:17.490439')"
    )
    conn.execute(
        "INSERT INTO materials VALUES ('material_1','meeting_1','transcript.pdf','pdf',"
        "?,'2025-11-11T15:20:32.114671')",
        ("x" * 4693,),
    )
    conn.execute(
        "INSERT INTO briefs VALUES ('brief_1','meeting_1','2025-11-11T15:20:47.000000',"
        "'gemini',?)",
        (json.dumps(LEGACY_BRIEF),),
    )
    conn.commit()
    conn.close()
    return path


# --- Adoption of an existing database --------------------------------------


def test_opening_a_legacy_database_migrates_it_without_losing_rows(legacy_db_path: Path):
    db = Database(legacy_db_path)

    assert db.schema_version() == LATEST_VERSION
    assert len(db.list_meetings()) == 1
    assert len(db.get_materials("meeting_1")) == 1
    assert len(db.get_brief_history("meeting_1")) == 1
    assert db.get_material("material_1").char_count == 4693


def test_legacy_briefs_still_validate_against_the_current_schema(legacy_db_path: Path):
    """Tightened validators must not retroactively reject stored history."""
    db = Database(legacy_db_path)
    brief = db.get_latest_brief("meeting_1").as_brief()

    assert brief.meeting_title == "Q4 Planning"
    assert brief.open_action_items[0].owner == "Ada"
    assert brief.total_agenda_minutes == 20


def test_legacy_rows_can_be_chunked_after_migration(legacy_db_path: Path):
    """The new table has to accept the materials that were already there."""
    from core.schema import NewChunk

    db = Database(legacy_db_path)
    ids = db.replace_chunks("material_1", [NewChunk(chunk_index=i, text=f"c{i}") for i in range(3)])

    assert len(ids) == 3
    assert db.count_chunks("meeting_1") == 3


def test_migration_runs_only_once_across_reopens(legacy_db_path: Path):
    Database(legacy_db_path)
    Database(legacy_db_path)
    db = Database(legacy_db_path)

    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM schema_version").fetchone()[0] == LATEST_VERSION


# --- Access patterns the un-migrated UI still uses -------------------------


def test_the_ui_can_index_records_like_dicts(legacy_db_path: Path):
    """Mirrors the subscripting in app.py; see `core.schema.Record`."""
    db = Database(legacy_db_path)

    meeting = db.list_meetings()[0]
    assert "{} ({})".format(meeting["title"], meeting["date"] or "No date") == (
        "AI engineering (2025-11-11)"
    )

    material = db.get_materials(meeting["id"])[0]
    assert material["filename"] == "transcript.pdf"
    assert material["char_count"] == 4693

    history = db.get_brief_history(meeting["id"])[0]
    assert "{} • {}".format(history["created_at"][:16], history["model"].upper()) == (
        "2025-11-11T15:20 • GEMINI"
    )


def test_the_ui_can_splat_a_stored_brief_into_the_model(legacy_db_path: Path):
    """app.py does `MeetingBrief(**brief_data["brief"])`."""
    db = Database(legacy_db_path)
    record = db.get_brief_by_id("brief_1")

    assert MeetingBrief(**record["brief"]).meeting_title == "Q4 Planning"


def test_the_orchestrator_pattern_of_matching_a_material_by_filename(legacy_db_path: Path):
    """Deduplication in `ingest_material` iterates summaries and compares fields."""
    db = Database(legacy_db_path)

    existing = next(
        (m["id"] for m in db.get_materials("meeting_1") if m["filename"] == "transcript.pdf"),
        None,
    )
    assert existing == "material_1"


def test_a_raw_connection_still_unpacks_rows_positionally(legacy_db_path: Path):
    """`core.document_handler` does `for material_id, text in rows`."""
    db = Database(legacy_db_path)
    conn = db.get_connection()
    try:
        rows = conn.execute(
            "SELECT id, text FROM materials WHERE meeting_id = ?", ("meeting_1",)
        ).fetchall()
        unpacked = [(material_id, len(text)) for material_id, text in rows]
    finally:
        conn.close()

    assert unpacked == [("material_1", 4693)]
