# Handoff — Chunk 2 complete, resume at Chunk 3

**Date:** 2026-07-28
**Branch:** `overhaul/langgraph-multi-agent`
**Status:** Chunks 1–2 of 8 complete. Chunk 1 is committed (`e5317f1`); Chunk 2 is
**uncommitted** in the working tree.

Read `handoffs/chunk1_implemented.md` for the architecture decisions, the full chunk
plan, and the environment facts — none of that is repeated here.

---

## What Chunk 2 delivered

| File | State |
|---|---|
| `core/schema.py` | Rewritten |
| `core/db.py` | Rewritten |
| `core/migrations.py` | New |
| `tests/test_schema.py`, `test_db.py`, `test_migrations.py`, `test_db_legacy_compat.py` | New |
| `.gitignore` | WAL sidecars + `data/briefs.backup-*.db` |

**129 tests pass** (was 36), `~7s`, still no network and no model downloads.
Ruff is down to 2 warnings, both in `core/document_handler.py` and
`core/llm_providers.py` — legacy files Chunks 3 and 4 rewrite. Leave them.

### `chunks` table

```sql
CREATE TABLE chunks (
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
```

`AUTOINCREMENT` is load-bearing, not stylistic. Verified empirically: a plain
`INTEGER PRIMARY KEY` reassigns `1` after you delete every row, so a re-chunk would
recycle a live FAISS vector id onto different text — the exact misalignment defect this
table exists to kill. With `AUTOINCREMENT` the id advances instead, so stale vectors
resolve to *nothing*, which is detectable. `tests/test_migrations.py` and
`tests/test_db.py` both pin this.

The `ON DELETE CASCADE` clauses also only fire because the repository now sets
`PRAGMA foreign_keys = ON` on every connection. Also verified empirically: with the
pragma off, cascades are silently ignored.

### `core/db.py` repository

Every method now goes through `connect()`, a `@contextmanager` that sets
`row_factory = sqlite3.Row`, enables foreign keys, tries WAL, and commits or rolls back
on exit. Rows come back as Pydantic records, not dicts.

New chunk API — this is what Chunk 3 consumes:

- `replace_chunks(material_id, [NewChunk, ...]) -> list[int]` — atomic swap of a
  material's whole chunk set; returns row ids **in input order**. These are the FAISS
  vector ids.
- `get_chunks_by_ids(ids, *, strict=False)` — **preserves the order of `ids`** because
  the caller is FAISS handing back a similarity ranking. `strict=True` raises
  `IndexOutOfSyncError` on missing ids; that is the mode retrieval should use.
  Batched at 500 params so a full-meeting sweep does not blow SQLite's bind limit.
- `get_neighbour_chunks(chunk_id, radius)` — neighbour expansion, matched by
  `chunk_index` **within the material**, never by arithmetic on row ids.
- `chunk_ids_for_meeting`, `get_chunks_for_material`, `get_chunks_for_meeting`,
  `count_chunks`, `delete_chunks_for_material`, `get_chunk`.

Also new: `get_material` (with text), `iter_material_texts`, `require_meeting`,
`delete_meeting`, `schema_version`.

Behaviour changes worth knowing:

- `add_material` / `save_brief` against a non-existent meeting now raise
  `MeetingNotFoundError`. They used to insert an unreachable row.
- `delete_material` no longer swallows exceptions; it returns `False` only for
  "not found".
- Ordering is `created_at DESC, rowid DESC` everywhere, so briefs written in the same
  second no longer come back in arbitrary order.

### `core/migrations.py`

Forward-only, `schema_version(version, name, applied_at)`, one transaction per
migration so a failure cannot advance the version. Three migrations: `1` baseline
(`IF NOT EXISTS`, so a pre-overhaul database is adopted in place untouched), `2` chunks,
`3` lookup indices on `materials`/`briefs`/`meetings`.

`backup_database(path)` uses SQLite's own backup API and falls back to a byte copy.

To add a migration: append to `MIGRATIONS`, never renumber, never edit a released one.

### `core/schema.py`

- **Records** (`Meeting`, `Material`, `MaterialSummary`, `Chunk`, `NewChunk`,
  `ScoredChunk`, `BriefRecord`, `BriefSummary`) mirror rows. Frozen, `extra="forbid"`,
  and deliberately **not** `str_strip_whitespace` — stripping `Chunk.text` would
  desynchronise `char_start`/`char_end` from the material body.
- **Brief structures** (`MeetingBrief`, `ActionItem`, `AgendaItem`, `Evidence`) are
  `extra="ignore"` and validate hard: `due` must be `YYYY-MM-DD`, `time_window` must be
  `YYYY-MM-DD..YYYY-MM-DD`, `minutes` in 1..480, statuses normalised
  (`Completed`/`in progress`/… → `done`/`open`), `null` lists absorbed to `[]`.
- `BriefRecord.brief` stays a **raw dict** on purpose. Briefs are written once and read
  for years; validating on read would mean a future schema tightening retroactively
  breaks stored history. Opt in with `record.as_brief()`.
- `Evidence.chunk_id: int | None` is already there for Chunk 3 to populate.

---

## The real database was migrated

`data/briefs.db` — backed up to `data/briefs.backup-20260728202338.db` (gitignored)
before anything ran. After migration:

- **5 meetings, 9 materials, 10 briefs** — unchanged, and row contents byte-compared
  against the pre-migration fingerprint, not just counted.
- `PRAGMA integrity_check` → `ok`; `PRAGMA foreign_key_check` → clean.
- All 10 stored briefs validate against the **tightened** `MeetingBrief`.
- Schema at v3, `journal_mode` now `wal`.
- `chunks` is empty — nothing has been ingested through the new path yet. Chunk 3
  backfills it.

---

## Start here: Chunk 3

Retrieval keyed on chunk row ids.

1. Rewrite chunking to emit `NewChunk`s with **real `char_start`/`char_end` offsets**
   into the material text. Nothing produces offsets yet; the fields exist and default
   to `char_start + len(text)`, which is only correct if you do not strip. The current
   `chunk_text` strips each chunk, so offsets and text will disagree unless you record
   the offsets before stripping. Use `settings.chunk_size` / `chunk_overlap` (900/150).
2. Replace `core/embed.py`'s bare `IndexFlatIP` with `faiss.IndexIDMap2`, adding vectors
   under the ids returned by `replace_chunks`. Ids are int64 — pass
   `np.asarray(ids, dtype="int64")`.
3. Rewrite `core/recall.py` to search the index, hydrate with
   `get_chunks_by_ids(..., strict=True)`, expand with `get_neighbour_chunks`, and return
   `ScoredChunk`s. Delete the re-chunk-at-query-time path in
   `core/document_handler.py` entirely — that positional correspondence is the bug.
4. Backfill: ingest the 9 existing materials into `chunks` and rebuild the five indices
   in `data/faiss/`. The old `.index` files are keyed on nothing meaningful; treat them
   as disposable and rebuild rather than migrate. Note the old files are named
   `{meeting_id}.index` while `settings.index_path()` returns `{meeting_id}.faiss` —
   pick one and clean up the other.
5. `tests/fakes.py::HashingEmbedder` is lexical, so you can assert real relevance
   ordering without downloading a model. Use it.

The load-bearing test to write first: **store chunks, index them, delete a material,
re-chunk, search, and assert you never get back text that belongs to a different
chunk than the id says.** That is the defect, stated as an assertion.

---

## Commands

```bash
.venv/Scripts/python.exe -m pytest
```

```bash
.venv/Scripts/python.exe -m ruff check core/ tests/ agents/
```

---

## Landmines (in addition to Chunk 1's, which all still apply)

- **`tests/test_db_legacy_compat.py` is a temporary file.** It pins the dict-style
  subscripting `app.py` and the orchestrator do against repository results, and the raw
  `get_connection()` positional unpacking `core/document_handler.py` does. It exists so
  the data layer can keep moving before the UI is rewritten. Delete it — along with
  `Record.__getitem__`/`get`/`__contains__` in `core/schema.py` and
  `Database.get_connection` — in Chunk 7.
- WAL mode means `data/briefs.db-wal` and `-shm` now appear next to the database. Both
  are gitignored. Do not commit them, and do not copy the `.db` alone if you need a
  manual backup — use `backup_database`.
- New rows use `utc_now_iso()` (tz-aware UTC); rows written before the overhaul used
  naive local time. String ordering still sorts them correctly by date, but do not
  assume `created_at` is parseable as a single format.
- The chunk store is empty. Anything that reads `chunks` before Chunk 3's backfill gets
  nothing — that is expected, not a bug.
