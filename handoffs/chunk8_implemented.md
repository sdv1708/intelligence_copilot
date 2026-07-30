# Handoff — Chunk 8 complete

**Date:** 2026-07-29
**Branch:** `feat/react-frontend`
**Status:** All seven phases done. Streamlit is gone; the app is FastAPI + React.

Read these first; none of their content is repeated here:

- **[handoffs/chunk8_plan.md](chunk8_plan.md)** — the seven-phase plan, all of it
  now delivered. Its Phase 1 endpoint table is stale (14 routes exist, not 11);
  `web/src/api/client.ts` and the README's API table are the accurate lists.
- **[handoffs/chunk8_part6_implemented.md](chunk8_part6_implemented.md)** — the
  Browser-pane notes, the `useRequest` reload landmine, the per-meeting lock, and
  the two techniques for exercising a costly POST. **All still stand** except the
  screenshot problem, which did not recur (see below).
- **`git show <this commit>`** — the reasoning is in the commit message.

---

## What Phase 7 changed

**Deleted:** `app.py` (1057 lines) and `.streamlit/config.toml`. The
`CopilotOrchestrator` facade **stays** — `api/` is its only caller now, and
`tests/test_orchestrator.py` pins its boundary translation.

**`scripts/serve.py`** — the single-port wrapper. `npm run build`, then
`uvicorn.run("api.main:app")` **as an import string**, because `mount_frontend()`
runs at import time and only mounts a bundle that already exists; importing the
app before the build would serve nothing until a restart. `--port`, `--host`,
`--skip-build`, `--build-only`. `mount_frontend` was not touched.

**`requirements.txt`** rewritten against the venv. Beyond what the Phase 6
handoff listed, two corrections to it:

- **`langchain` (the umbrella) is genuinely needed** — `agents/planner.py:149`
  imports `create_agent` from it. It is not redundant with `langchain-core`.
- **`pydantic-settings` was in the wrong file.** `core/config.py:18` imports it,
  so it is a runtime dependency, but it was pinned only in `requirements-dev.txt`
  — meaning `pip install -r requirements.txt` alone produced an app that could
  not import. Moved.

Also: `numpy` and `starlette` added (both imported directly); `sqlmodel`,
`pandas` and `streamlit` dropped; `torch` deliberately left **unpinned** with a
comment — `sentence-transformers` requires it and an exact pin fights
platform/CUDA wheel selection. `pytest-asyncio` dropped from dev, and this was
**proved, not assumed**: `pytest -p no:asyncio` gives 437 passed.

**`README.md`** rewritten (606 lines changed). The old "API Reference" documented
orchestrator *methods*; it is now the 14 HTTP endpoints, with the two that cost
tokens marked. Added the success/error asymmetry, the per-meeting lock, the
`chunks.id` AUTOINCREMENT-is-a-vector-id rule, and both run modes.

**Configs:** `.claude/launch.json`'s `copilot` entry (Streamlit on 8501) is now
`api` (uvicorn on 8077, `--reload`). `.devcontainer/devcontainer.json` gains a
Node 24 feature, installs `requirements-dev.txt`, and runs `scripts.serve` on
8000 instead of Streamlit on 8501.

---

## Things found on the way that the plan did not ask for

- **`.gitignore`'s unanchored `lib/` was real and is now fixed.** Verified
  concretely rather than reasoned about: `touch web/src/lib/probe.ts` was matched
  by `.gitignore:21`, so a `web/src/lib/` of frontend source would have been
  silently uncommittable. Every packaging entry is now anchored with a leading
  `/`, and a comment says why. Re-tested after: the probe shows as `??`.
  `git check-ignore` on a **non-existent** path returns nothing, which is why
  this looked fine at first — create the file before testing.
- **`env.example` documented two settings that do not exist.** `NGROK_TOKEN`
  (uncommented, so a user would set it and expect something) and
  `MAX_UPLOAD_SIZE` — the latter was mirroring `maxUploadSize` from the
  Streamlit config. Both removed; the remaining 19 variables were each checked
  against a real `Settings` field.
- **Nine files carried stranded prose, not the six the last handoff listed.**
  It missed `agents/runtime.py:38`, `core/db.py:62`, `core/embed.py:60`,
  `core/logging_config.py:28` and `tests/test_prompts.py:169` — all
  *present-tense* justifications resting on Streamlit behaviour. Past-tense
  history ("Streamlit got this for free from `st.cache_resource`" in
  `api/deps.py:3`, and the same in `api/translate.py`, `api/schemas.py`) was
  **kept deliberately**: it is accurate and explains why the code is shaped the
  way it is.

## Still open

- **`has_api_key` in `/api/health` is a length check, not a validity check.**
  Seven phases have now survived on that; a placeholder still renders as
  "API key: Present". The fix is in `core/config.py` and remains unmade. No plan
  asked for it, so it was not done — but nothing else will ask either.
- **No live provider call has been made in any chunk of this overhaul.** Blocked
  on a key, not on permission: `OPENAI_API_KEY` and `ANTHROPIC_API_KEY` in `.env`
  are `your_..._here` placeholders and the one real `GEMINI_API_KEY` 401s. Phase
  7 needed no model call. **Do not ask the user to paste a key into the chat** —
  they add it to `.env` and you confirm by running. `has_api_key` is not proof.
- **`web/` still has no test harness.** Three files of pure functions now want
  one: `brief.ts`, `format.ts`, and `QaPanel.tsx`'s module-private `citations`.

---

## Verification

```bash
.venv/Scripts/python.exe -m pytest
```

```bash
.venv/Scripts/python.exe -m ruff check core/ tests/ agents/ scripts/ api/
```

```bash
npm run typecheck --prefix web
```

**437 tests pass** (~39s, unchanged — Phase 7 deleted no tests and added none),
ruff clean, frontend typechecks. `pytest -q` still prints no summary line in this
environment; drop `-q` for the count.

### How the single-port script was verified

Not just built — **served and driven**. `web/dist` was deleted first, rebuilt via
`scripts.serve --build-only`, then served on port 8123 against the real
`data/briefs.db`:

| Checked | Result |
|---|---|
| `GET /` | 200 `text/html` |
| `GET /assets/index-*.js` | 200 `text/javascript` |
| `GET /api/health` | live JSON, gemini/cpu |
| unknown non-`/api` GET | 200 HTML — SPA fallback works |
| `GET /api/nope` | **404 `application/json`** — the `serves_index` scoping rule holds |

Then through the Browser pane on the real database: selected the "AI strategy"
meeting, which loaded two indexed PDFs and a stored brief (10 action items,
recalled from storage, Markdown/JSON exports present). **Six API requests, all
same-origin on 8123** — no Vite proxy, no CORS. **Zero console errors.**

Also exercised: `--skip-build` with no bundle exits 1 with a message rather than
silently starting an API-only server, and `--build-only` stops without importing
uvicorn.

**The database is untouched — 5 meetings, 9 materials, 10 briefs, 872 chunks**,
exactly as Phase 6 left it. Every request was a GET.

### Browser-pane note, updated again

Phase 6 reported screenshots failing on *every* attempt. This session they were
**not needed and not attempted** — `get_page_text`, `read_page`,
`read_console_messages` and `read_network_requests` covered everything, and
`read_network_requests` in particular is the tool that proves same-origin
serving. Prefer it to a screenshot for this kind of check. `read_page
{filter: "interactive"}` listed the sidebar buttons without labels (`ref_2`…
`ref_7`); clicking `ref_3` selected a meeting, so positional guessing worked, but
`get_page_text` after the click is what confirms which one.

---

## Suggested next steps

- **`review`** — suggested at the Phase 4, 5 and 6 boundaries and taken at none.
  The diff is now four phases wide and this one is 1570 deletions.
- **Merge.** `main` is still untouched at `72bd17f` and the standing decision was
  *do not merge without asking again*. Chunk 8 is finished, so that ask is now
  due.
- **The live provider call**, if the user adds a working key.
