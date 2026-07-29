"""Migration runner behaviour, including adoption of a pre-migration database."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from core.exceptions import StorageError
from core.migrations import (
    LATEST_VERSION,
    MIGRATIONS,
    backup_database,
    current_version,
    migrate,
)


@pytest.fixture
def conn(tmp_path: Path):
    connection = sqlite3.connect(tmp_path / "test.db")
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    yield connection
    connection.close()


def _table_names(connection: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }


def test_versions_are_sequential_and_unique():
    versions = [m.version for m in MIGRATIONS]
    assert versions == list(range(1, len(MIGRATIONS) + 1))
    assert len({m.name for m in MIGRATIONS}) == len(MIGRATIONS)


def test_fresh_database_starts_at_zero(conn):
    assert current_version(conn) == 0


def test_migrate_creates_every_table(conn):
    assert migrate(conn) == LATEST_VERSION
    assert {"meetings", "materials", "briefs", "chunks", "schema_version"} <= _table_names(
        conn
    )


def test_migrate_is_idempotent(conn):
    migrate(conn)
    applied = conn.execute("SELECT COUNT(*) FROM schema_version").fetchone()[0]

    assert migrate(conn) == LATEST_VERSION
    assert conn.execute("SELECT COUNT(*) FROM schema_version").fetchone()[0] == applied


def test_every_migration_is_recorded_with_its_name(conn):
    migrate(conn)
    rows = conn.execute("SELECT version, name FROM schema_version ORDER BY version").fetchall()
    assert [(r["version"], r["name"]) for r in rows] == [
        (m.version, m.name) for m in MIGRATIONS
    ]


def test_adopts_a_pre_migration_database_without_losing_rows(conn):
    """The v1 baseline must recognise a schema the old code created."""
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
        INSERT INTO meetings VALUES ('m1', 'Legacy', '2025-01-01', 'a', NULL, '2025-01-01T00:00:00');
        INSERT INTO materials VALUES ('mat1', 'm1', 'f.txt', 'txt', 'hello', '2025-01-01T00:00:00');
        INSERT INTO briefs VALUES ('b1', 'm1', '2025-01-01T00:00:00', 'gemini', '{"meeting_title": "Legacy"}');
        """
    )
    conn.commit()

    assert migrate(conn) == LATEST_VERSION

    assert conn.execute("SELECT COUNT(*) FROM meetings").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM materials").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM briefs").fetchone()[0] == 1
    assert conn.execute("SELECT title FROM meetings WHERE id='m1'").fetchone()[0] == "Legacy"
    assert "chunks" in _table_names(conn)


def test_refuses_a_database_from_a_newer_build(conn):
    migrate(conn)
    conn.execute(
        "INSERT INTO schema_version VALUES (?, 'from the future', '2099-01-01T00:00:00')",
        (LATEST_VERSION + 5,),
    )
    conn.commit()

    with pytest.raises(StorageError, match=r"only.*knows up to"):
        migrate(conn)


def test_a_failing_migration_leaves_the_previous_version_intact(conn, monkeypatch):
    """Version must not advance past a migration that raised."""
    from core import migrations

    def explode(_: sqlite3.Connection) -> None:
        raise sqlite3.OperationalError("no such column: nope")

    broken = migrations.Migration(LATEST_VERSION + 1, "broken", explode)
    monkeypatch.setattr(migrations, "MIGRATIONS", (*MIGRATIONS, broken))
    monkeypatch.setattr(migrations, "LATEST_VERSION", broken.version)

    with pytest.raises(StorageError, match="broken"):
        migrations.migrate(conn)

    assert migrations.current_version(conn) == LATEST_VERSION


def test_chunk_ids_are_never_reused(conn):
    """AUTOINCREMENT, not rowid reuse -- a recycled id is a mismatched vector."""
    migrate(conn)
    conn.execute(
        "INSERT INTO meetings VALUES ('m1','T',NULL,NULL,NULL,'2025-01-01T00:00:00')"
    )
    conn.execute(
        "INSERT INTO materials VALUES ('mat1','m1','f.txt','txt','body','2025-01-01T00:00:00')"
    )
    for i in range(3):
        conn.execute(
            "INSERT INTO chunks (material_id, meeting_id, chunk_index, text, "
            "char_start, char_end, created_at) VALUES ('mat1','m1',?,?,0,1,'t')",
            (i, f"chunk {i}"),
        )
    conn.commit()
    highest = conn.execute("SELECT MAX(id) FROM chunks").fetchone()[0]

    conn.execute("DELETE FROM chunks")
    conn.execute(
        "INSERT INTO chunks (material_id, meeting_id, chunk_index, text, "
        "char_start, char_end, created_at) VALUES ('mat1','m1',0,'fresh',0,1,'t')"
    )
    conn.commit()

    assert conn.execute("SELECT MAX(id) FROM chunks").fetchone()[0] > highest


def test_backup_copies_the_file_and_leaves_the_original(tmp_path: Path):
    db_path = tmp_path / "briefs.db"
    connection = sqlite3.connect(db_path)
    connection.execute("CREATE TABLE t (x TEXT)")
    connection.execute("INSERT INTO t VALUES ('keep me')")
    connection.commit()
    connection.close()

    backup = backup_database(db_path, suffix="test")

    assert backup is not None
    assert backup.exists()
    assert db_path.exists()
    restored = sqlite3.connect(backup)
    assert restored.execute("SELECT x FROM t").fetchone()[0] == "keep me"
    restored.close()


def test_backup_of_a_missing_file_is_a_no_op(tmp_path: Path):
    assert backup_database(tmp_path / "absent.db") is None
