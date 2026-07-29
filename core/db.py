"""SQLite repository for meetings, materials, chunks and briefs.

What changed from the original implementation, and why:

* **Connections are context-managed.** Every method previously opened a
  connection and closed it on the happy path only, so any exception leaked the
  handle and left the write uncommitted with no error surfaced.
* **`PRAGMA foreign_keys = ON` is actually set.** The schema declared foreign
  keys from the start; SQLite ignores them unless the pragma is enabled per
  connection, so they had never once been enforced. Deleting a material now
  removes its chunks instead of orphaning them.
* **`row_factory = sqlite3.Row`.** The old code addressed columns positionally
  (`row[3]`), which meant any change to a `SELECT *` silently reassigned every
  field downstream.
* **Rows come back as Pydantic records**, not bare dicts, so a typo in a field
  name fails where it is written rather than rendering as `None` in the UI.

The `chunks` table is the substantive addition. Chunks used to be recomputed
from the material text at query time and matched to FAISS results by list
position — a correspondence nothing maintained. Chunks are now rows with
stable integer primary keys, and those keys are what the vector index stores.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from core.config import Settings, get_settings
from core.exceptions import IndexOutOfSyncError, MeetingNotFoundError, StorageError
from core.logging_config import get_logger
from core.migrations import LATEST_VERSION, current_version, migrate
from core.schema import (
    BriefRecord,
    BriefSummary,
    Chunk,
    Material,
    MaterialSummary,
    Meeting,
    NewChunk,
)
from core.utils import generate_id, utc_now_iso

logger = get_logger(__name__)

_CHUNK_COLUMNS = (
    "id, material_id, meeting_id, chunk_index, text, char_start, char_end, created_at"
)

# Conservative bound on bound parameters per statement; older SQLite builds cap
# at 999.
_MAX_PARAMS = 500


class Database:
    """Repository over the application's SQLite file.

    Cheap to construct and safe to build per Streamlit rerun: no connection is
    held open between calls, which also sidesteps SQLite's rule that a
    connection may not cross threads.
    """

    def __init__(
        self,
        db_path: str | Path | None = None,
        *,
        settings: Settings | None = None,
        migrate_on_open: bool = True,
    ) -> None:
        if db_path is not None:
            self.db_path = Path(db_path).resolve()
        else:
            self.db_path = Path((settings or get_settings()).db_path).resolve()

        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        if migrate_on_open:
            self.init_db()

    # --- Connection management ---------------------------------------------

    def _new_connection(self) -> sqlite3.Connection:
        try:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
        except sqlite3.Error as exc:
            raise StorageError(f"Cannot open database at {self.db_path}: {exc}") from exc

        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            # WAL lets the UI read while an ingestion writes. Not available on
            # every filesystem, so a failure here is informational, not fatal.
            conn.execute("PRAGMA journal_mode = WAL")
        except sqlite3.Error as exc:
            logger.debug("Could not enable WAL on %s: %s", self.db_path, exc)
        return conn

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """Yield a configured connection, committing or rolling back on exit."""
        conn = self._new_connection()
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    # --- Schema -------------------------------------------------------------

    def init_db(self) -> int:
        """Bring the schema up to date. Returns the resulting version.

        Deliberately not routed through `connect()`: `migrate` manages a
        transaction per migration, and nesting those inside an outer one would
        make a failure commit the migrations that preceded it in the same
        block.
        """
        conn = self._new_connection()
        try:
            version = migrate(conn)
        finally:
            conn.close()
        logger.debug("Database ready at %s (schema v%d)", self.db_path, version)
        return version

    def schema_version(self) -> int:
        conn = self._new_connection()
        try:
            with conn:
                return current_version(conn)
        finally:
            conn.close()

    @property
    def latest_schema_version(self) -> int:
        return LATEST_VERSION

    # --- Meetings -----------------------------------------------------------

    def create_meeting(
        self,
        title: str,
        date: str | None = None,
        attendees: str | None = None,
        tags: str | None = None,
    ) -> str:
        meeting_id = generate_id("meeting")
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO meetings (id, title, date, attendees, tags, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (meeting_id, title, date, attendees, tags, utc_now_iso()),
            )
        logger.info("Created meeting %s (%s)", meeting_id, title)
        return meeting_id

    def get_meeting(self, meeting_id: str) -> Meeting | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM meetings WHERE id = ?", (meeting_id,)
            ).fetchone()
        return Meeting(**dict(row)) if row else None

    def require_meeting(self, meeting_id: str) -> Meeting:
        """Like `get_meeting`, but raises instead of returning `None`."""
        meeting = self.get_meeting(meeting_id)
        if meeting is None:
            raise MeetingNotFoundError(meeting_id)
        return meeting

    def list_meetings(self) -> list[Meeting]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM meetings ORDER BY created_at DESC, rowid DESC"
            ).fetchall()
        return [Meeting(**dict(row)) for row in rows]

    def delete_meeting(self, meeting_id: str) -> bool:
        """Delete a meeting and, by cascade, its chunks.

        Materials and briefs predate `ON DELETE CASCADE` and are removed
        explicitly; their chunks go with the materials.
        """
        with self.connect() as conn:
            conn.execute("DELETE FROM briefs WHERE meeting_id = ?", (meeting_id,))
            conn.execute("DELETE FROM chunks WHERE meeting_id = ?", (meeting_id,))
            conn.execute("DELETE FROM materials WHERE meeting_id = ?", (meeting_id,))
            cursor = conn.execute("DELETE FROM meetings WHERE id = ?", (meeting_id,))
            deleted = cursor.rowcount > 0
        if deleted:
            logger.info("Deleted meeting %s and everything under it", meeting_id)
        return deleted

    # --- Materials ----------------------------------------------------------

    def add_material(
        self, meeting_id: str, filename: str, media_type: str, text: str
    ) -> str:
        material_id = generate_id("material")
        try:
            with self.connect() as conn:
                conn.execute(
                    """
                    INSERT INTO materials (id, meeting_id, filename, media_type, text, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (material_id, meeting_id, filename, media_type, text, utc_now_iso()),
                )
        except sqlite3.IntegrityError as exc:
            # Now that foreign keys are enforced, attaching a material to a
            # meeting that does not exist fails here rather than creating a row
            # nothing can ever find.
            raise MeetingNotFoundError(meeting_id) from exc

        logger.info(
            "Added material %s (%s, %d chars) to meeting %s",
            material_id,
            filename,
            len(text),
            meeting_id,
        )
        return material_id

    def get_material(self, material_id: str) -> Material | None:
        """Fetch one material including its full text."""
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT id, meeting_id, filename, media_type,
                       COALESCE(text, '') AS text, created_at
                FROM materials WHERE id = ?
                """,
                (material_id,),
            ).fetchone()
        return Material(**dict(row)) if row else None

    def get_materials(self, meeting_id: str) -> list[MaterialSummary]:
        """List a meeting's materials without loading their text bodies."""
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, meeting_id, filename, media_type,
                       LENGTH(COALESCE(text, '')) AS char_count, created_at
                FROM materials
                WHERE meeting_id = ?
                ORDER BY created_at DESC, rowid DESC
                """,
                (meeting_id,),
            ).fetchall()
        return [MaterialSummary(**dict(row)) for row in rows]

    def material_counts(self) -> dict[str, int]:
        """How many materials each meeting holds, keyed by meeting id.

        The meeting list needs a count beside every row. Asking `get_materials`
        once per meeting would be a query per row for a number SQLite can group
        in one pass — and `get_materials` also computes `LENGTH(text)` over every
        body, which is real work to throw away.

        Meetings with no materials are absent rather than zero; callers read
        this with `.get(id, 0)`.
        """
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT meeting_id, COUNT(*) AS n FROM materials GROUP BY meeting_id"
            ).fetchall()
        return {row["meeting_id"]: row["n"] for row in rows}

    def brief_counts(self) -> dict[str, int]:
        """How many briefs each meeting has, keyed by meeting id."""
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT meeting_id, COUNT(*) AS n FROM briefs GROUP BY meeting_id"
            ).fetchall()
        return {row["meeting_id"]: row["n"] for row in rows}

    def iter_material_texts(self, meeting_id: str) -> list[Material]:
        """All materials for a meeting, with text. Used by ingestion and recall."""
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, meeting_id, filename, media_type,
                       COALESCE(text, '') AS text, created_at
                FROM materials
                WHERE meeting_id = ?
                ORDER BY created_at, rowid
                """,
                (meeting_id,),
            ).fetchall()
        return [Material(**dict(row)) for row in rows]

    def delete_material(self, material_id: str) -> bool:
        """Delete a material. Its chunks cascade away with it."""
        with self.connect() as conn:
            cursor = conn.execute("DELETE FROM materials WHERE id = ?", (material_id,))
            deleted = cursor.rowcount > 0

        if deleted:
            logger.info("Deleted material %s and its chunks", material_id)
        else:
            logger.warning("Material not found, nothing deleted: %s", material_id)
        return deleted

    # --- Chunks -------------------------------------------------------------

    def replace_chunks(
        self, material_id: str, chunks: Sequence[NewChunk]
    ) -> list[int]:
        """Make `chunks` the complete chunk set for `material_id`.

        Returns the assigned row ids in the same order as `chunks`. Those ids
        are what Chunk 3 hands to `faiss.IndexIDMap2` as vector ids.

        Replacement is a single transaction: a material is never briefly
        half-chunked, so a concurrent read cannot see a partial set. Ids are
        never reused (the table is `AUTOINCREMENT`), so vectors left in the
        index from the previous chunking resolve to nothing rather than to the
        wrong text — a detectable inconsistency instead of a silent one.
        """
        with self.connect() as conn:
            row = conn.execute(
                "SELECT meeting_id FROM materials WHERE id = ?", (material_id,)
            ).fetchone()
            if row is None:
                raise StorageError(
                    f"Cannot store chunks: no material with id '{material_id}'."
                )
            meeting_id = row["meeting_id"]

            conn.execute("DELETE FROM chunks WHERE material_id = ?", (material_id,))

            created_at = utc_now_iso()
            ids: list[int] = []
            for chunk in chunks:
                cursor = conn.execute(
                    """
                    INSERT INTO chunks (
                        material_id, meeting_id, chunk_index,
                        text, char_start, char_end, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        material_id,
                        meeting_id,
                        chunk.chunk_index,
                        chunk.text,
                        chunk.char_start,
                        chunk.char_end,
                        created_at,
                    ),
                )
                ids.append(int(cursor.lastrowid))

        logger.info("Stored %d chunks for material %s", len(ids), material_id)
        return ids

    def get_chunk(self, chunk_id: int) -> Chunk | None:
        with self.connect() as conn:
            row = conn.execute(
                f"SELECT {_CHUNK_COLUMNS} FROM chunks WHERE id = ?", (chunk_id,)
            ).fetchone()
        return Chunk(**dict(row)) if row else None

    def get_chunks_by_ids(
        self, chunk_ids: Sequence[int], *, strict: bool = False
    ) -> list[Chunk]:
        """Fetch chunks by id, preserving the order of `chunk_ids`.

        Order matters because the caller is usually FAISS, handing back ids
        sorted by similarity. Ids that no longer exist are dropped, or — with
        `strict=True` — raise `IndexOutOfSyncError`, which is what retrieval
        wants: an index pointing at deleted chunks is a bug to fix, not a
        result set to quietly shorten.
        """
        if not chunk_ids:
            return []

        by_id: dict[int, Chunk] = {}
        with self.connect() as conn:
            # Batched because SQLite caps the number of bound parameters, and a
            # consistency sweep can ask about every chunk in a meeting at once.
            for start in range(0, len(chunk_ids), _MAX_PARAMS):
                batch = tuple(chunk_ids[start : start + _MAX_PARAMS])
                placeholders = ",".join("?" * len(batch))
                rows = conn.execute(
                    f"SELECT {_CHUNK_COLUMNS} FROM chunks WHERE id IN ({placeholders})",
                    batch,
                ).fetchall()
                by_id.update({row["id"]: Chunk(**dict(row)) for row in rows})

        missing = [cid for cid in chunk_ids if cid not in by_id]
        if missing:
            message = (
                f"{len(missing)} of {len(chunk_ids)} chunk ids are not in the "
                f"chunk store (first few: {missing[:5]}). The vector index "
                f"references chunks that no longer exist."
            )
            if strict:
                raise IndexOutOfSyncError(message)
            logger.warning(message)

        return [by_id[cid] for cid in chunk_ids if cid in by_id]

    def get_chunks_for_material(self, material_id: str) -> list[Chunk]:
        with self.connect() as conn:
            rows = conn.execute(
                f"SELECT {_CHUNK_COLUMNS} FROM chunks "
                "WHERE material_id = ? ORDER BY chunk_index",
                (material_id,),
            ).fetchall()
        return [Chunk(**dict(row)) for row in rows]

    def get_chunks_for_meeting(self, meeting_id: str) -> list[Chunk]:
        with self.connect() as conn:
            rows = conn.execute(
                f"SELECT {_CHUNK_COLUMNS} FROM chunks "
                "WHERE meeting_id = ? ORDER BY material_id, chunk_index",
                (meeting_id,),
            ).fetchall()
        return [Chunk(**dict(row)) for row in rows]

    def chunk_ids_for_meeting(self, meeting_id: str) -> list[int]:
        """Just the ids — enough to check an index against the store."""
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT id FROM chunks WHERE meeting_id = ? ORDER BY id", (meeting_id,)
            ).fetchall()
        return [int(row["id"]) for row in rows]

    def get_neighbour_chunks(self, chunk_id: int, radius: int = 1) -> list[Chunk]:
        """Chunks adjacent to `chunk_id` within the same material.

        This is how breadth is restored after the move to small,
        embedding-sized chunks: retrieve precisely, then widen. Neighbours are
        found by `chunk_index` within the material, not by arithmetic on the
        row id, so they stay correct after any re-chunking.
        """
        if radius <= 0:
            return []

        with self.connect() as conn:
            anchor = conn.execute(
                "SELECT material_id, chunk_index FROM chunks WHERE id = ?", (chunk_id,)
            ).fetchone()
            if anchor is None:
                return []

            rows = conn.execute(
                f"""
                SELECT {_CHUNK_COLUMNS} FROM chunks
                WHERE material_id = ?
                  AND chunk_index BETWEEN ? AND ?
                  AND id != ?
                ORDER BY chunk_index
                """,
                (
                    anchor["material_id"],
                    anchor["chunk_index"] - radius,
                    anchor["chunk_index"] + radius,
                    chunk_id,
                ),
            ).fetchall()
        return [Chunk(**dict(row)) for row in rows]

    def count_chunks(self, meeting_id: str | None = None) -> int:
        with self.connect() as conn:
            if meeting_id is None:
                row = conn.execute("SELECT COUNT(*) AS n FROM chunks").fetchone()
            else:
                row = conn.execute(
                    "SELECT COUNT(*) AS n FROM chunks WHERE meeting_id = ?",
                    (meeting_id,),
                ).fetchone()
        return int(row["n"])

    def delete_chunks_for_material(self, material_id: str) -> int:
        """Remove a material's chunks, leaving the material itself in place."""
        with self.connect() as conn:
            cursor = conn.execute(
                "DELETE FROM chunks WHERE material_id = ?", (material_id,)
            )
            return cursor.rowcount

    # --- Briefs -------------------------------------------------------------

    def save_brief(
        self, meeting_id: str, model: str, brief_dict: dict[str, Any]
    ) -> str:
        brief_id = generate_id("brief")
        try:
            with self.connect() as conn:
                conn.execute(
                    """
                    INSERT INTO briefs (id, meeting_id, created_at, model, brief_json)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        brief_id,
                        meeting_id,
                        utc_now_iso(),
                        model,
                        json.dumps(brief_dict, ensure_ascii=False),
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise MeetingNotFoundError(meeting_id) from exc

        logger.info("Saved brief %s for meeting %s", brief_id, meeting_id)
        return brief_id

    def get_latest_brief(self, meeting_id: str) -> BriefRecord | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT id, meeting_id, created_at, model, brief_json FROM briefs
                WHERE meeting_id = ?
                ORDER BY created_at DESC, rowid DESC
                LIMIT 1
                """,
                (meeting_id,),
            ).fetchone()
        return _brief_record(row) if row else None

    def get_brief_by_id(self, brief_id: str) -> BriefRecord | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT id, meeting_id, created_at, model, brief_json
                FROM briefs WHERE id = ?
                """,
                (brief_id,),
            ).fetchone()
        return _brief_record(row) if row else None

    def get_brief_history(self, meeting_id: str) -> list[BriefSummary]:
        """Brief metadata, newest first, without deserialising the payloads."""
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, meeting_id, created_at, model FROM briefs
                WHERE meeting_id = ?
                ORDER BY created_at DESC, rowid DESC
                """,
                (meeting_id,),
            ).fetchall()
        return [BriefSummary(**dict(row)) for row in rows]


def _brief_record(row: sqlite3.Row) -> BriefRecord:
    """Build a `BriefRecord`, tolerating a payload that is not valid JSON.

    A brief row whose JSON has been corrupted should not take down the history
    list; it comes back with an empty payload and a logged error.
    """
    try:
        payload = json.loads(row["brief_json"])
    except (TypeError, json.JSONDecodeError) as exc:
        logger.error("Brief %s has unreadable JSON: %s", row["id"], exc)
        payload = {}

    if not isinstance(payload, dict):
        logger.error("Brief %s does not contain a JSON object", row["id"])
        payload = {}

    return BriefRecord(
        id=row["id"],
        meeting_id=row["meeting_id"],
        created_at=row["created_at"],
        model=row["model"],
        brief=payload,
    )
