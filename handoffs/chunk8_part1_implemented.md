# Handoff — Chunk 8 Phase 1 complete, resume at Phase 2

**Date:** 2026-07-29
**Branch:** `feat/react-frontend` (branched from `main` @ `72bd17f`)
**Status:** Phase 1 of 7 complete and committed at `a521b98`. Working tree clean.

Read these first; none of their content is repeated here:

- **[handoffs/chunk8_plan.md](chunk8_plan.md)** — the seven-phase plan, the decisions
  behind it, and the endpoint table. This is the spec for the rest of the work.
- **`git show a521b98`** — what Phase 1 delivered and why the non-obvious parts are
  the way they are (the per-meeting lock, the error table's ordering, the two new
  repository methods).
- **[handoffs/chunk7_implemented.md](chunk7_implemented.md)** and its predecessors —
  architecture, data layer, retrieval, providers, the LangGraph core, the facade.

---

## The decision waiting for you

The last thing asked of the user was **"Phase 2 (API tests) next, or skip to Phase 3
and see the frontend sooner?"** They ran `/handoff` instead of answering. **That
choice is still open — ask before assuming.**

Phase 2 is the safer order (the API gets pinned before a UI is built on it). Phase 3
first is the more motivating order for a hackathon, and nothing in Phase 3 depends on
Phase 2 existing.

---

## The other open question, carried since Chunk 6

**No live LLM call has been made in any chunk of this overhaul, including this one.**
The supervisor's tool-calling loop, `Synthesizer.brief` against a real provider, and
the trace for a *freshly generated* brief remain exercised only against fakes.

Phase 1's brief and Q&A endpoints were verified for wiring and preconditions only —
a 422 when a meeting has no materials, correct locking, correct translation. The
happy path through them has never run.

It costs real tokens against the key in `.env`. **Ask before spending them.**

---

## Environment facts added by Phase 1

Installed into `.venv` and **not yet in `requirements.txt`** (that file is rewritten
in Phase 7, and it is still wrong in the ways Chunk 1 recorded — it pins
`langchain==0.3.7` against a venv holding `1.0.5`):

```
fastapi 0.140.13   uvicorn 0.51.0   python-multipart 0.0.32
```

For Phase 3: **Node v24.15.0, npm 11.12.1** are on the machine.

Run the API with:

```bash
.venv/Scripts/python.exe -m uvicorn api.main:app --port 8077 --reload
```

Interactive docs at `/docs`. Port 8077 is arbitrary — it is what Phase 1's smoke
tests used. `web/vite.config.ts` does not exist yet; when you write it, the CORS
allowlist in `api/main.py` already expects Vite on **5173**.

---

## What the real data actually looks like

`data/briefs.db` is gitignored and holds **5 meetings, 9 materials, 10 briefs** —
verified unchanged after Phase 1's smoke tests, which created and deleted their own
rows. Design the UI against these, because they are what will be demoed:

- Titles have **trailing spaces** (`"Q4 "`, `"check in "`). Do not trust them to be
  trimmed; the records layer deliberately does not strip stored values.
- `tags` is empty on four of five meetings, and the fifth is a typo (`"palnning"`).
  A tag chip row will be empty most of the time — design for that, not around it.
- `attendees` are short and informal (`"sanj"`, `"a, b, c"`).
- Materials run to **268,347 characters**. `MaterialOut.char_count` needs thousands
  separators and the filename column needs to truncate.
- `filename` and `media_type` are nullable in the schema and **null on real rows**.
  `MaterialOut.of` substitutes `"Untitled"` / `"unknown"` so no client has to.
- Brief history is up to 3 versions on one meeting, all `model: "gemini"`.

---

## Landmines specific to this phase

- **`app.routes` does not list included routes in FastAPI 0.140.** Routers are wrapped
  in `_IncludedRouter` objects, so the usual `for r in app.routes: print(r.path)`
  introspection prints only `/docs` and `/openapi.json` and looks like nothing
  registered. It is fine. Verify routes by hitting them, or read `/openapi.json`.

- **`mount_frontend()` runs at import time in `api/main.py`** and currently returns
  `False` because `web/dist/` does not exist. Once Phase 3 builds a bundle it will
  start mounting `/assets` and registering an SPA fallback. That fallback replaces
  the handler for *every* `StarletteHTTPException`; it is scoped to return
  `index.html` only for non-`/api` GET 404s, and everything else falls through to a
  JSON body. **If you touch it, keep that scoping** — without it an unknown API route
  returns the HTML shell with status 200 and every frontend typo looks like a
  successful request returning nonsense.

- **The per-meeting lock is held across the whole brief run** — tens of seconds. That
  is deliberate (`Retriever.recall` writes the index via `ensure_meeting_indexed`, so
  a concurrent upload would race it), and it means the UI must not offer to upload to
  a meeting while its brief is generating. Disable those controls in Phase 4/5 rather
  than letting requests queue invisibly.

- **`api/schemas.py` re-exports `MeetingBrief` from `core.schema` rather than
  redeclaring it.** Do not create a parallel definition for the frontend's benefit;
  hand-write the TypeScript from it in Phase 3 and let it be the single source.

- Chunks 1–7's landmines all still apply. In particular: **a real `.env` with live
  API keys sits in the repo root.** It is gitignored. Never echo it. The test suite
  neutralises it via `tests/conftest.py` and `tests/test_conftest_isolation.py`
  guards that — do not weaken it, or the suite reads live credentials and passes for
  the wrong reason.

---

## Verification baseline

```bash
.venv/Scripts/python.exe -m pytest
```

```bash
.venv/Scripts/python.exe -m ruff check core/ tests/ agents/ scripts/ api/
```

**368 tests pass** (~31s, no network, no model downloads) and ruff is clean. Phase 1
added no tests — that is Phase 2's job. `api/` is inside the ruff scope; `app.py`
still is not, and it is deleted in Phase 7 rather than fixed.

---

## Suggested skills for the next session

- **`tdd`** — for Phase 2. `tests/fakes.py` already has `HashingEmbedder` (lexical and
  deterministic, so retrieval assertions are real) and `ScriptedChatModel`. The
  behaviours worth writing first are the status-code table in `api/errors.py`, the
  partial-failure path in a multi-file upload, and the `ok`/`warning` asymmetry
  between `brief_response` and `qa_response` in `api/translate.py`.

- **`artifact-design`** — before Phase 3. The user's brief is "looks like the ChatGPT
  website, clean and simple, no emojis but clean symbols". Calibrate against that
  rather than reaching for the gradients and shadow stacks the old `app.py` used.

- **`dataviz`** — for Phase 5 only, if the trace timeline grows anything chart-shaped
  (per-specialist hit/neighbour counts are the obvious candidate). Read it before
  choosing colours, not after.

- **`run`** — Phases 3–6. Drive the Vite dev server through the Browser pane and
  screenshot; do not ask the user to check manually.

- **`review`** — worth running at the Phase 6 boundary, before Phase 7's deletions
  make the diff large.

---

## Prompt for the next session

> Continue Chunk 8 of the LangGraph overhaul of `D:\hackathon\intelligence_copilot`,
> on branch `feat/react-frontend`. Read `handoffs/chunk8_part1_implemented.md` first,
> then `handoffs/chunk8_plan.md` for the phase plan.
>
> Phase 1 (the FastAPI layer over the orchestrator facade) is done and committed at
> `a521b98`, verified against the real `data/briefs.db`. 368 tests pass, ruff clean.
>
> Ask me whether to do Phase 2 (API tests) or skip to Phase 3 (the React shell) — I
> have not answered that yet. Also ask before making any live LLM call; none has been
> made in this entire overhaul and it spends real tokens.
>
> Use `.venv/Scripts/python.exe`, not a bare `python`. Keep going phase by phase and
> commit at each boundary; do not attempt the rest of the chunk in one pass.
