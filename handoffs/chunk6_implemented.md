# Handoff — Chunk 6 complete, resume at Chunk 7

**Date:** 2026-07-29
**Branch:** `main` (chunks 1–4 committed: `e5317f1`, `f4691fb`, `96509ca`, `691f3ec`, `54569b8`)
**Status:** Chunks 1–6 of 8 complete. Chunks 5 and 6 are **uncommitted** in the working tree.

Read `handoffs/chunk1_implemented.md` for the architecture decisions and environment
facts, `chunk2` for the data layer, `chunk3` for retrieval, `chunk4` for providers and
synthesis, and `chunk5` for the LangGraph core. None of that is repeated here.

---

## What Chunk 6 delivered

The compatibility facade, and `app.py` actually wired to it.

| File | State |
|---|---|
| `agents/copilot_orchestrator.py` | Rewritten — a facade over the graphs, no pipeline logic left |
| `app.py` | Wired to the facade; `core/synth` import gone; trace surfaced |
| `tests/test_orchestrator.py` | New — 20 tests on the boundary translation |
| `.claude/launch.json` | New — lets the `run` skill start the app |

**360 tests pass** (was 340), `~31s`, still no network and no model downloads in the
suite. `ruff check core/ tests/ agents/ scripts/` is **clean** — the 16 `.format()`
warnings Chunk 5 left behind went with the rewritten orchestrator.

---

## The facade

`CopilotOrchestrator` keeps the five method names `app.py` calls and delegates:

```
ingest_material      -> parse -> store -> index_material          (the whole write path)
recall_context_tool  -> Retriever.recall + format_context
generate_brief       -> run_brief_graph(runtime, ...)  -> dict
answer_question      -> run_qa_graph(runtime, ...)     -> dict
recall_previous_brief-> db.get_latest_brief().as_brief()
```

One `CopilotRuntime` is built in `__init__` and shared by every call, so a session has
one chat client, one loaded embedder and one database handle. `__init__` also takes
`runtime=` — that keyword is the whole reason the facade is testable without a key, and
`tests/test_orchestrator.py` uses nothing else.

`db`, `retriever`, `synthesizer`, `provider_name` and `model_name` are now properties
onto the runtime rather than attributes, so there is exactly one of each.

### The two places `success` is not the whole story

Both were decided in Chunk 5 and are easy to erase by accident, so both have a test.

| Situation | `success` | Why |
|---|---|---|
| Brief generated, storage failed | **True**, with `error` set | The document is usable. Throwing it away because SQLite was locked serves nobody. `app.py` reads both and shows a warning above the brief. |
| Q&A retrieved nothing | **True** | "I could not find relevant information" is a real answer, and it costs no model call. |
| Q&A retrieval *failed* | **False** | The graph lands on the same `no_context` node either way. Reporting an index error as a polite non-answer would hide it, so the facade — not the graph — draws this line. |

`generate_brief` also returns `notes`, `plan`, `plan_source`, `plan_rationale`,
`failed_tasks`, `chunks`, and the whole `BriefRun` under `"run"`. Chunk 8 should read
`run` rather than re-deriving anything from the flat keys.

---

## What changed in `app.py`

1. **`core/synth` is no longer imported.** `load_prompt_template` and `generate_brief`
   were both dead imports there — the app never called either — so the import was
   deleted rather than repointed at `core/prompts`. **`core/synth.py` now has no
   importer anywhere in the codebase.** Chunk 7 deletes the module outright.
   `core.recall.recall_context` / `format_context_blocks` were dead imports too and went
   with them.

2. **Ingestion is one call.** `app.py` used to parse the file, `db.add_material` it, and
   *then* call `ingest_material` — which parsed it a second time, found the row it had
   just written by filename, and indexed that. Two consequences, both fixed:
   - every document was parsed twice;
   - uploading the same filename twice left **two** material rows and two copies of the
     document in the index, so the meeting's evidence was silently doubled.

   `ingest_material` now owns the whole write path. `_store_material` reuses the row for
   a filename whose text is unchanged, and deletes the row *and its chunks and vectors*
   when the text has changed, before adding the new version. Three tests pin this.

3. **The trace is on screen.** `render_trace` renders `run.notes` in a
   "🔬 How this was produced" expander under the brief, and under each Q&A answer. This
   is what replaces the `log_message("[Step 2]")` calls that went to a terminal nobody
   running the app was looking at. Plan source, task names and evidence size render as
   badges next to the brief.

4. **`brief_result` is new session state.** The result dict is kept because the trace and
   any post-generation error do not survive the `st.rerun()` after the button press. It
   is cleared everywhere `generated_brief` is cleared, and deliberately set to `None`
   when a brief is *loaded* from history — a stored brief has no run behind it, so
   showing a trace for it would be a lie.

5. **The demo-mode banner was a bug.** `os.path.exists("/tmp")` is true on every Unix
   machine, so users were told their data was temporary when it was not. It now warns
   only when `Settings.prepare_storage` actually relocated storage into the temp
   directory.

6. Smaller repairs on the same pass: `b['model'].upper()` and `mat['media_type'].upper()
   ` both crashed on a `NULL` column; history loading now goes through
   `BriefRecord.as_brief()`; `init_orchestrator` reads the provider from `Settings`
   rather than `os.getenv`.

`app.py` still uses `.format()` throughout and is still outside the ruff scope, as in
every previous chunk. Chunk 8 rewrites it.

---

## Verified

**Offline, against a copy of the real `data/briefs.db`** (5 meetings, 872 chunks), with
the real MiniLM embedder and a scripted chat model. The real database was not written to.

- Ingest of a new document: stored, chunked, indexed, and immediately searchable.
- Re-upload of identical bytes: same `material_id`, still one material row.
- Re-upload of changed bytes: one row, new text, no chunk of the old text left, index
  still consistent with the store.
- Brief on the 822-chunk transcript: five specialists, 27 hits merged, capped to 60
  chunks, stored, and the full nine-line trace came back on the result dict.
- `recall_previous_brief` read it back; Q&A returned 12 sources.

**In the running app** (`streamlit run app.py`, driven in a browser):

- Boots, loads the embedder, and builds a real Gemini client:
  `Orchestrator ready: provider=gemini model=models/gemini-2.5-flash supervisor=on`.
- Meeting selection, materials library, Q&A panel and brief area all render against real
  records — the `Record.__getitem__` shim is still carrying `app.py`.
- **"Recall Previous" ran end to end**, loading a stored brief through `as_brief()` and
  rendering every section.

**No live API call has been made, in this chunk or any previous one.** The user was asked
and chose not to make one. So these remain exercised only against fakes:

- the supervisor's tool-calling loop and structured-output path;
- `Synthesizer.brief` against a real provider;
- the trace and badge rendering for a *freshly generated* brief (the data is proven, the
  Streamlit rendering of it is not).

That is still the highest-value next verification, and it still needs the user's sign-off.

---

## Start here: Chunk 7

Delete the dead code the facade has now orphaned.

1. **Delete `core/synth.py`.** Nothing imports it. It is the last thing pulling
   `google.generativeai` into the dependency graph.
2. **Delete `Record.__getitem__` / `get` / `__contains__`** from `core/schema.py`, and
   convert `app.py` to attribute access (`meeting.title`, not `meeting['title']`).
   `tests/test_db_legacy_compat.py` exists to be deleted with them.
3. **Delete `core.recall.recall_context` and `_database_behind`**, and
   `Database.get_connection` with them — the raw-connection shim has no callers left.
   `tests/test_recall.py::test_recall_context_*` go too.
4. **Delete `core.llm_providers.get_llm_provider`**; the facade calls `build_chat_model`
   through `CopilotRuntime.build`.
5. `core/utils.log_message` is still used by `core/parsing.py`. Either convert parsing to
   the structured logger or leave both; do not half-convert.

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

## Landmines (in addition to Chunks 1–5's, which still apply)

- **`generate_brief` returning `success=True` does not mean the brief was saved.** Read
  `error`. A caller that only checks `success` will report a lost brief as a stored one.
- **`answer_question` and `generate_brief` disagree on what an error means**, on purpose
  (table above). Do not "fix" one to match the other without reading why.
- **`ingest_material` matches an existing material by filename alone.** Two genuinely
  different documents uploaded under the same name are treated as a revision of each
  other, and the first is deleted. That is the right default for a re-upload and the
  wrong one for a careless name collision; there is no content hash behind it.
- **`_store_material` deletes before it writes.** If `add_material` fails after the old
  row is gone, the meeting has lost that document. The alternative — write first, delete
  after — leaks a duplicate on failure instead. Neither is transactional across SQLite
  and FAISS, which is the real constraint.
- **The `"run"` key holds a `BriefRun`, which holds `ScoredChunk`s, which hold the full
  text of every retrieved chunk.** It is in Streamlit session state. On a long transcript
  that is a few hundred KB per generation, per session.
- **`render_trace` escapes `<`, `>` and `&` by hand** because the surrounding UI passes
  `unsafe_allow_html=True`. Trace lines contain retrieved query text. Anything else that
  renders `notes` must escape them too.
- **`CopilotOrchestrator.__init__` builds a chat client, which needs an API key.**
  Constructing the facade raises `MissingAPIKeyError` before any method is called, and in
  the app that surfaces inside `@st.cache_resource`. It is not a brief-generation
  failure, however it reads.
- **`.claude/launch.json` hardcodes `.venv/Scripts/python.exe` and port 8501.** Windows
  paths; a non-Windows checkout needs `.venv/bin/python`.
