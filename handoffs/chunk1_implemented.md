# Handoff — Chunk 1 complete, resume at Chunk 2

**Date:** 2026-07-28
**Branch:** `overhaul/langgraph-multi-agent` (branched from `main` @ `e1c90c0`)
**Status:** Chunk 1 of 8 complete. Nothing committed yet — all work is uncommitted in the working tree.

---

## What this project is becoming

`intelligence_copilot` is a Streamlit app that ingests meeting materials, indexes them, and
generates executive meeting briefs + Q&A. The user asked for a **massive overhaul into a genuine
LangChain/LangGraph multi-agent project**, delivered **in discrete chunks, not all at once**.

Two decisions the user made explicitly — do not re-litigate:

1. **LangGraph supervisor + specialist agent nodes.** Chosen over tool-calling-agents-only and
   over plain LCEL chains. Deterministic edges where the pipeline is fixed; tool-calling agents
   where judgment is needed.
2. **Backend first, UI last.** `app.py` must keep working end-to-end throughout, via a
   compatibility facade that preserves the old `CopilotOrchestrator` method signatures. The
   Streamlit rewrite is the final chunk.

Background detail lives in project memory (auto-loads for this project):
`~/.claude/projects/D--hackathon-intelligence-copilot/memory/` —
`overhaul-langgraph-multi-agent.md` and `copilot-known-defects.md`.

---

## Chunk plan

| # | Chunk | State |
|---|---|---|
| 1 | Foundation: config, logging, exceptions, test scaffolding | **Done** |
| 2 | Data layer: persisted `chunks` table + repository | **Next** |
| 3 | Retrieval: FAISS `IndexIDMap2` keyed on chunk row ids | Pending |
| 4 | LLM providers + prompts (`with_structured_output`) | Pending |
| 5 | LangGraph multi-agent core | Pending |
| 6 | Compatibility facade + wire `app.py` | Pending |
| 7 | Cleanup: dead code, requirements, docs | Pending |
| 8 | Streamlit UI rewrite | Pending |

---

## What Chunk 1 delivered

New files — read these first, they are the foundation everything else sits on:

- `core/config.py` — typed `Settings` (pydantic-settings). Derived paths, `api_key_for()`,
  `prepare_storage()`, `get_settings()` (lru_cached), `reset_settings_cache()`.
- `core/exceptions.py` — error hierarchy. `IndexOutOfSyncError` exists specifically for Chunk 3.
- `core/logging_config.py` — `configure_logging()` / `get_logger()`, idempotent under Streamlit reruns.
- `tests/fakes.py` — `HashingEmbedder` (deterministic, *lexical*, so retrieval tests can assert real
  relevance ordering with no model download) and `ScriptedChatModel`.
- `tests/conftest.py`, `tests/test_*.py`, `pyproject.toml` (pytest + ruff config).

Rewritten: `core/utils.py` — `generate_id`, `utc_now_iso`, `timer`, plus **transitional shims**
(`get_env`, `get_storage_path`, `log_message`) that exist only to keep the not-yet-migrated modules
running. Delete them in Chunk 7 once nothing imports them.

**36 tests pass** (`~0.3s`, no network, no model downloads). Legacy modules all still import; the
Streamlit app is unbroken.

---

## Start here: Chunk 2

Goal: give every chunk a **stable primary key** so a FAISS vector id can map to exactly one row of
text. This is the root fix for the retrieval-misalignment defect.

Concretely:

1. Add a `chunks` table (`id` INTEGER PRIMARY KEY AUTOINCREMENT, `material_id`, `meeting_id`,
   `chunk_index`, `text`, `char_start`/`char_end`, `created_at`). The integer PK is what
   `faiss.IndexIDMap2` will use as its vector id in Chunk 3 — FAISS ids must be int64.
2. Rework `core/db.py` `Database` into a repository: context-managed connections
   (`contextlib.contextmanager`), `PRAGMA foreign_keys = ON` (currently declared but never
   enforced), indices on `meeting_id`, and `row_factory = sqlite3.Row` to kill the positional
   `row[0]`/`row[1]` indexing used throughout.
3. Lightweight forward-only migration with a `schema_version` table.
4. Revamp `core/schema.py` Pydantic models — richer validation, and models for the new chunk rows.
5. Tests against a `tmp_path` SQLite file.

**Migration must be non-destructive.** Real data exists at `data/briefs.db`:
**5 meetings, 9 materials, 10 briefs.** Verify counts survive. Back the file up before running
anything destructive.

---

## Environment facts you will need

- Interpreter is the venv: `.venv/Scripts/python.exe` (Windows, Git Bash available).
  **Do not assume a bare `python`.**
- Venv is **Python 3.13.5** while `.python-version` says `3.11` — unreconciled, flagged for Chunk 7.
- `requirements.txt` is **badly out of sync** with the venv (pins `langchain==0.3.7`; venv has
  `1.0.5`). Trust the venv, fix the file in Chunk 7.
- Installed and verified working: `langchain 1.0.5`, `langchain-core 1.0.4`, `langgraph 1.0.2`,
  `faiss-cpu 1.12.0`, `sentence-transformers 5.1.2`, `streamlit 1.51.0`, `pydantic 2.12.4`.
- Added during Chunk 1: `pydantic-settings`, `pytest`, `pytest-asyncio`, `ruff`.
- APIs confirmed present for Chunk 5: `langchain.agents.create_agent`, `langgraph.graph.StateGraph`,
  `langgraph.checkpoint.memory.InMemorySaver`, `BaseChatModel.with_structured_output`,
  `langchain_core.tools.tool`.

Commands:

```bash
.venv/Scripts/python.exe -m pytest
```

```bash
.venv/Scripts/python.exe -m ruff check core/ tests/ agents/
```

---

## Landmines

- **A real `.env` with live API keys sits in the repo root.** It is gitignored — keep it that way.
  Never echo its contents. `tests/conftest.py` neutralises it for the suite
  (`monkeypatch.setitem(Settings.model_config, "env_file", None)`); `tests/test_conftest_isolation.py`
  guards that. Do not weaken it — without it the suite reads live credentials and passes for the
  wrong reason.
- **Chunk size vs the embedder.** `all-MiniLM-L6-v2` truncates at 256 word-pieces (~1000 chars).
  The old 4000-char chunks had ~75% of each chunk invisible to search. New defaults are 900/150;
  breadth is restored by neighbour expansion at retrieval time, not by bigger chunks. Do not raise
  `chunk_size` past ~1000 without changing the embedding model.
- **`prompts/system_prompt.txt` is polluted** — after the JSON rules it contains a full duplicate of
  the user prompt plus a chat-session changelog, all currently sent as the system message. Chunk 4.
- ~36 ruff warnings remain, **all in legacy files** (`.format()` calls etc.) that Chunks 2–4 rewrite.
  New code is clean. Don't bulk-fix legacy files that are about to be replaced — I did this once in
  Chunk 1 and it widened the diff for no benefit.
- `core/synth.py` is dead except `load_prompt_template`; it imports `google.generativeai`, which is
  not in requirements. Delete in Chunk 7.

---

## Suggested skills for the next session

- **`tdd`** — Chunks 2 and 3 are the correctness core of the overhaul (id mapping, migration
  integrity). Write the failing test first; the scaffolding in `tests/` is built for exactly this.
- **`claude-api`** — load before Chunk 4. That chunk sets model IDs for Anthropic/OpenAI/Gemini and
  the current ones are stale (`claude-3-5-sonnet-20241022`, `gpt-4` with an impossible
  `max_tokens=30000`). Do not pick model IDs from memory.
- **`review`** — worth running at the Chunk 3 and Chunk 6 boundaries, before the diff gets large.
- **`run`** — for Chunk 6, to confirm the Streamlit app genuinely boots and generates a brief
  end-to-end rather than just importing.

---

## Prompt for the next session

> Continue the LangGraph multi-agent overhaul of `D:\hackathon\intelligence_copilot`.
> Read `handoffs/chunk1_implemented.md` first — Chunk 1 (config, logging, exceptions, test
> scaffolding) is done on branch `overhaul/langgraph-multi-agent`, 36 tests passing.
>
> Start Chunk 2: the persisted chunk store. Add a `chunks` table with an integer primary key that
> FAISS `IndexIDMap2` can use as its vector id, rework `core/db.py` into a proper repository
> (context-managed connections, `PRAGMA foreign_keys = ON`, `sqlite3.Row`, indices), add a
> forward-only migration with a `schema_version` table, and revamp the Pydantic models. Write tests
> as you go using the existing `tests/` fixtures.
>
> The migration must preserve the real data in `data/briefs.db` — 5 meetings, 9 materials,
> 10 briefs. Back it up first and verify the counts afterwards.
>
> Use `.venv/Scripts/python.exe`, not a bare `python`. Keep going chunk by chunk; don't attempt the
> whole overhaul at once.
