# Handoff — Chunk 7 complete, resume at Chunk 8

**Date:** 2026-07-29
**Branch:** `main` (chunks 1–6 committed, ending at `f80b366`)
**Status:** Chunks 1–7 of 8 complete. Chunk 7 is **uncommitted** in the working tree.

Read `handoffs/chunk1_implemented.md` for the architecture decisions and environment
facts, `chunk2` for the data layer, `chunk3` for retrieval, `chunk4` for providers and
synthesis, `chunk5` for the LangGraph core, and `chunk6` for the facade and the `app.py`
rewiring. None of that is repeated here.

---

## What Chunk 7 delivered

The dead code the facade orphaned is gone. **There are no transitional shims left in the
codebase.**

| Deleted | Where it lived |
|---|---|
| `core/synth.py` (whole module) | the pre-overhaul Gemini path |
| `Record.__getitem__` / `get` / `__contains__` | `core/schema.py` |
| `recall_context` / `_database_behind` | `core/recall.py` |
| `Database.get_connection` | `core/db.py` |
| `get_llm_provider` | `core/llm_providers.py` |
| `log_message` / `get_env` / `get_storage_path` | `core/utils.py` |
| `parse_pasted_text` | `core/parsing.py` |

**368 tests pass** (was 360), `~33s`, still no network and no model downloads in the
suite. `ruff check core/ tests/ agents/ scripts/` is clean.

---

## The two judgement calls

Chunk 6's instructions said to delete `tests/test_db_legacy_compat.py` outright and to
convert `core/parsing.py` "or leave both". Neither was followed literally; both are worth
knowing about.

**1. `tests/test_db_legacy_compat.py` was cut down, not deleted.** Half of it pinned the
subscripting and raw connections the un-migrated UI used, and that half went. The other
half adopts a database in exactly the shape the pre-overhaul code wrote — three tables, no
`schema_version`, no `chunks` — and asserts every row survives. That is `data/briefs.db`
in miniature, the migrations are forward-only, and no other test covers it. It is about
legacy *data*, which outlives the legacy *code*, so it stayed. The file's docstring now
says so.

**2. `core/parsing.py` was converted, and given tests.** It was the last importer of
`log_message`, so leaving it would have meant keeping the whole shim section of
`core/utils.py` alive for one module. Converting it emptied that section entirely.

The conversion is not purely mechanical: `log_message("ERROR", f"...: {e!s}")` recorded
`str(exc)` and dropped the traceback, and `str(exc)` on a `pypdf` read error is routinely
empty — so the log line was literally `Failed to parse PDF: `. It is now
`logger.exception`, which keeps the traceback. `tests/test_parsing.py` is new (13 tests);
the module previously had none, which is why nothing noticed the log lines were useless.

`parse_pasted_text` went with the same pass. It has had no caller since Chunk 6 routed
pasted text through `ingest_material` as a `.txt` upload with `media_type="pasted"`
supplied by `app.py`.

---

## `app.py` now reads records by attribute

Sixteen subscripts became attribute access. Nothing else in `app.py` changed — it still
uses `.format()` throughout, is still outside the ruff scope, and Chunk 8 still rewrites
it.

One behaviour change came with it: `mat['filename']` on a `NULL` filename rendered the
string `None` in the materials library; `mat.filename or 'Untitled'` does not. This is the
same class of defect as the `NULL` `media_type` crash Chunk 6 fixed two lines below it.

`tests/test_schema.py` now asserts a subscript raises `TypeError`, rather than asserting
it works. That is the guard against the shim coming back: with `get()` gone, a typo'd key
can no longer quietly return a default.

---

## Verified

**Full suite and ruff**, as above.

**In the running app** (`streamlit run app.py`, driven in a browser, against the real
`data/briefs.db`: 5 meetings, 5 briefs across 3 of them). Every path converted to
attribute access was exercised on real rows:

- the meeting dropdown rendered all five titles and dates, including one with a `NULL`
  tags column and one whose title has a trailing space;
- the "Selected" card (`title` / `date` / `created_at`) and the header status card;
- the 📚 History block — `2025-11-08T19:57 • GEMINI` is `b.created_at[:16]` and
  `(b.model or 'unknown model').upper()`;
- **"📖 Load" ran end to end**: `brief_history[i].id` → `get_brief_by_id` → `as_brief()`,
  and every section of the stored brief rendered;
- the Materials Library rendered `filename`, `media_type`, `char_count`, `created_at` and
  the per-row delete key across a PDF and a pasted-text material.

No browser console errors, no server-side errors, and the page still boots after the
parsing rewrite.

**No live API call has been made, in this chunk or any previous one.** The user was asked
in Chunk 6 and chose not to. So these remain exercised only against fakes:

- the supervisor's tool-calling loop and structured-output path;
- `Synthesizer.brief` against a real provider;
- the trace and badge rendering for a *freshly generated* brief.

That is still the highest-value next verification, and it still needs the user's sign-off.

---

## Start here: Chunk 8

Rewrite `app.py`. It is the last file outside the ruff scope and the last one using
`.format()` string-building with `unsafe_allow_html=True` everywhere.

The specific things Chunk 8 inherits:

1. **Read `result["run"]`, not the flat keys.** `generate_brief` returns the whole
   `BriefRun` under `"run"`; `notes`, `plan`, `failed_tasks` and `chunks` are flattened
   copies kept only so the current UI works. Same for `answer_question` and `QaRun`.
2. **`render_trace` escapes `<`, `>` and `&` by hand** because everything around it passes
   `unsafe_allow_html=True`. Trace lines contain retrieved query text. If the rewrite
   drops `unsafe_allow_html`, the hand-escaping goes too — but not before.
3. **The `Record.__getitem__` shim is gone**, so any new UI code reads records by
   attribute. There is no fallback if it guesses a field name wrong, which is the point.
4. **`README.md` is the last stale document, and it is only partly stale.** `guide/`,
   `deployment/` and the root `context.md` were deleted after this chunk (see the commit
   following it), and the README references to them went with the folders. What is left
   in it still describes the pre-overhaul design in places: the logging section documents
   `[INFO]` / `[OK]` string prefixes that `core.logging_config` replaced, and the agent
   prefixes `[IngestionTool]` / `[RecallTool]` name classes that no longer exist. Fix it
   alongside the UI rewrite, when the screenshots would need retaking anyway.

---

## Commands

```bash
.venv/Scripts/python.exe -m pytest
```

```bash
.venv/Scripts/python.exe -m ruff check core/ tests/ agents/ scripts/
```

```bash
.venv/Scripts/python.exe -m streamlit run app.py
```

---

## Landmines (in addition to Chunks 1–6's, which still apply)

- **`google-generativeai` is no longer imported anywhere.** It is still installed as a
  transitive dependency of `langchain-google-genai`. Do not read its presence in the
  environment as evidence that anything uses it directly.
- **`core/parsing.py` still swallows every exception and returns `""`.** That contract is
  deliberate and `ingest_material` depends on it — it is the single place a failed upload
  is reported to the user. A parser that starts raising will surface as an unhandled
  exception in the Streamlit callback instead.
- **`Database.connect()` is now the only way to get a connection**, and it commits or
  rolls back on exit. Code that wanted a long-lived cursor used `get_connection`; there is
  no longer an escape hatch, on purpose.
- **`tests/test_db_legacy_compat.py` protects a data shape, not a code path.** Deleting it
  because "the legacy code is gone" would remove the only coverage of adopting the real
  `data/briefs.db`.
