"""Forward-only schema migrations for the SQLite store.

The previous approach was a pile of `CREATE TABLE IF NOT EXISTS` statements run
on every startup. That works exactly once: it can create a schema but it can
never change one, so any later alteration would have silently not happened on
an existing database while passing on a fresh one.

This module records what has been applied in a `schema_version` table and
applies only what is missing. Migrations are forward-only by design — there is
no `down()`. Rolling a schema back on a single-file embedded database is better
served by restoring the backup that `backup_database` writes.

Rules for adding a migration:

* Append to `MIGRATIONS`; never renumber or edit a released one.
* Each migration must be safe to run against a database that already contains
  production data, and must leave existing rows intact.
"""

from __future__ import annotations

import shutil
import sqlite3
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

from core.exceptions import StorageError
from core.logging_config import get_logger
from core.utils import utc_now_iso

logger = get_logger(__name__)


class Migration(NamedTuple):
    """One numbered, irreversible schema step."""

    version: int
    name: str
    apply: Callable[[sqlite3.Connection], None]


# --- Individual migrations --------------------------------------------------


def _v1_baseline(conn: sqlite3.Connection) -> None:
    """The three original tables.

    Written with `IF NOT EXISTS` so that a database created by the pre-migration
    code is adopted at version 1 without its data being touched.
    """
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS meetings (
            id          TEXT PRIMARY KEY,
            title       TEXT NOT NULL,
            date        TEXT,
            attendees   TEXT,
            tags        TEXT,
            created_at  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS materials (
            id          TEXT PRIMARY KEY,
            meeting_id  TEXT NOT NULL,
            filename    TEXT,
            media_type  TEXT,
            text        TEXT,
            created_at  TEXT NOT NULL,
            FOREIGN KEY (meeting_id) REFERENCES meetings(id)
        );

        CREATE TABLE IF NOT EXISTS briefs (
            id          TEXT PRIMARY KEY,
            meeting_id  TEXT NOT NULL,
            created_at  TEXT NOT NULL,
            model       TEXT,
            brief_json  TEXT NOT NULL,
            FOREIGN KEY (meeting_id) REFERENCES meetings(id)
        );
        """
    )


def _v2_chunks(conn: sqlite3.Connection) -> None:
    """The persisted chunk store.

    `AUTOINCREMENT` is load-bearing rather than decorative. Without it SQLite
    assigns `max(id) + 1`, so deleting the last chunk and inserting a new one
    reuses the id — and that id is a FAISS vector id. A stale vector would then
    resolve to unrelated text, which is precisely the retrieval-misalignment
    defect this table exists to eliminate. AUTOINCREMENT makes ids monotonic
    and never reused.

    `ON DELETE CASCADE` only fires when `PRAGMA foreign_keys = ON`, which the
    repository sets on every connection.
    """
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS chunks (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            material_id  TEXT NOT NULL,
            meeting_id   TEXT NOT NULL,
            chunk_index  INTEGER NOT NULL,
            text         TEXT NOT NULL,
            char_start   INTEGER NOT NULL DEFAULT 0,
            char_end     INTEGER NOT NULL DEFAULT 0,
            created_at   TEXT NOT NULL,
            UNIQUE (material_id, chunk_index),
            FOREIGN KEY (material_id) REFERENCES materials(id) ON DELETE CASCADE,
            FOREIGN KEY (meeting_id)  REFERENCES meetings(id)  ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_chunks_meeting
            ON chunks (meeting_id, material_id, chunk_index);
        CREATE INDEX IF NOT EXISTS idx_chunks_material
            ON chunks (material_id, chunk_index);
        """
    )


def _v3_lookup_indices(conn: sqlite3.Connection) -> None:
    """Indices for the lookups the app performs on every page render.

    `materials` and `briefs` were only ever indexed on their primary keys, so
    every sidebar render and every brief-history fetch was a full table scan
    over rows that include quarter-megabyte transcripts.
    """
    conn.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_materials_meeting
            ON materials (meeting_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_briefs_meeting
            ON briefs (meeting_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_meetings_created
            ON meetings (created_at DESC);
        """
    )


MIGRATIONS: tuple[Migration, ...] = (
    Migration(1, "baseline_meetings_materials_briefs", _v1_baseline),
    Migration(2, "chunks_table", _v2_chunks),
    Migration(3, "lookup_indices", _v3_lookup_indices),
)

LATEST_VERSION: int = MIGRATIONS[-1].version


# --- Runner -----------------------------------------------------------------


def _ensure_version_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            version     INTEGER PRIMARY KEY,
            name        TEXT NOT NULL,
            applied_at  TEXT NOT NULL
        )
        """
    )


def current_version(conn: sqlite3.Connection) -> int:
    """Highest applied migration, or 0 for an unmanaged database."""
    _ensure_version_table(conn)
    row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
    return row[0] or 0


def migrate(conn: sqlite3.Connection) -> int:
    """Apply every pending migration. Returns the resulting version.

    Each migration runs inside its own transaction, so a failure half way
    through leaves the database at the last version that fully succeeded rather
    than in an undescribed state.
    """
    version = current_version(conn)
    if version > LATEST_VERSION:
        raise StorageError(
            f"Database is at schema version {version}, but this build only "
            f"knows up to {LATEST_VERSION}. Upgrade the application."
        )

    pending = [m for m in MIGRATIONS if m.version > version]
    if not pending:
        logger.debug("Schema up to date at version %d", version)
        return version

    for migration in pending:
        try:
            with conn:
                migration.apply(conn)
                conn.execute(
                    "INSERT INTO schema_version (version, name, applied_at) VALUES (?, ?, ?)",
                    (migration.version, migration.name, utc_now_iso()),
                )
        except sqlite3.Error as exc:
            raise StorageError(
                f"Migration {migration.version} ({migration.name}) failed: {exc}"
            ) from exc
        logger.info("Applied migration %d: %s", migration.version, migration.name)
        version = migration.version

    return version


def backup_database(db_path: Path | str, suffix: str | None = None) -> Path | None:
    """Copy the database file next to itself before a migration.

    Returns the backup path, or `None` if there was nothing to back up. Uses
    SQLite's own backup API so an in-flight writer cannot produce a torn copy.
    """
    db_path = Path(db_path)
    if not db_path.exists():
        return None

    stamp = suffix or datetime.now().strftime("%Y%m%d%H%M%S")
    target = db_path.with_name(f"{db_path.stem}.backup-{stamp}{db_path.suffix}")

    source = sqlite3.connect(db_path)
    try:
        destination = sqlite3.connect(target)
        try:
            source.backup(destination)
        finally:
            destination.close()
    except sqlite3.Error:
        # A locked or corrupt database still deserves a byte copy.
        shutil.copy2(db_path, target)
    finally:
        source.close()

    logger.info("Backed up %s to %s", db_path, target)
    return target
