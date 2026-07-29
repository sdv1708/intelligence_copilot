"""A database written by the pre-migration code is adopted in place.

This is the `data/briefs.db` scenario in miniature: three tables, no
`schema_version`, no `chunks`, and rows that must all still be there afterwards.
The migrations are forward-only, so getting this wrong is not recoverable by
re-running anything.

The other half of this file — the dict-style subscripting and raw connections
the un-migrated UI used — went with those shims in Chunk 7. What remains has
nothing to do with legacy *code*; it is about legacy *data*, which outlives it.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from core.db import Database
from core.migrations import LATEST_VERSION

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


def test_a_migrated_material_can_still_be_matched_by_filename(legacy_db_path: Path):
    """`ingest_material` deduplicates a re-upload against the rows already there.

    A meeting adopted from the old database is the case where that matters
    most: those materials predate the chunk store entirely.
    """
    db = Database(legacy_db_path)

    existing = next(
        (m.id for m in db.get_materials("meeting_1") if m.filename == "transcript.pdf"),
        None,
    )
    assert existing == "material_1"
