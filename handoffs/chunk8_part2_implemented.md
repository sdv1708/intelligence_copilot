# Handoff — Chunk 8 Phase 2 complete, resume at Phase 3

**Date:** 2026-07-29
**Branch:** `feat/react-frontend`, pushed and in sync with `origin/feat/react-frontend`
**Status:** Phases 1–2 of 7 complete. Working tree clean at `b60a79f`.

Read these first; none of their content is repeated here:

- **[handoffs/chunk8_plan.md](chunk8_plan.md)** — the seven-phase plan and the
  decisions behind it. Still the spec for the rest of the work.
- **[handoffs/chunk8_part1_implemented.md](chunk8_part1_implemented.md)** — what the
  real database looks like, the environment facts, and the landmines from Phase 1.
  **All of it still applies.** In particular the notes on trailing spaces in titles,
  empty `tags`, null `filename`/`media_type`, and the 268k-character material are
  design input for Phase 3 and are not restated below.
- **`git show b60a79f`** — what Phase 2 delivered and why the harness is shaped the
  way it is.
- **[handoffs/chunk7_implemented.md](chunk7_implemented.md)** and its predecessors —
  architecture, data layer, retrieval, providers, the LangGraph core, the facade.

---

## The decision from the last handoff, now resolved

Part 1 asked: "Phase 2 (API tests) or skip to Phase 3?" The user chose **Phase 2**,
and it is done. **Phase 3 (the React shell) is next** and nothing blocks it.

## The question still open, carried since Chunk 6

**No live LLM call has been made in any chunk of this overhaul, including this one.**
Phase 2 used fakes throughout, so the supervisor's tool-calling loop,
`Synthesizer.brief` against a real provider, and the trace for a *freshly generated*
brief remain unexercised against anything real.

It costs real tokens against the key in `.env`. **Ask before spending them.** Phases
5 and 6 are the natural moment.

---

## What Phase 2 changed in Phase 1's code

Two edits, both surfaced by writing the tests:

- **`serves_index(method, path, status_code)` extracted** from `spa_fallback` in
  [api/main.py](../api/main.py). It holds the rule that keeps an unknown `/api` path
  a JSON 404 instead of the HTML shell. It was extracted because the handler can only
  be registered by mounting a built bundle into the global `app`, which a test must
  not do. **This matters to you** — see the landmine below.
- `HTTP_422_UNPROCESSABLE_ENTITY` → `HTTP_422_UNPROCESSABLE_CONTENT` in
  `api/routes/briefs.py` and `api/routes/qa.py`. The old name is deprecated in this
  FastAPI version and the suite reported it.

## How the API tests are wired, if you need to extend them

[tests/test_api.py](../tests/test_api.py) — 69 tests, of 437 total.

The one thing that will bite you if you don't know it: **the `TestClient` is
deliberately never used as a context manager.** Entering it runs the lifespan, which
calls `deps.startup()` and would load the real embedding model and read the real
provider config. The `wire` fixture monkeypatches `api.deps`' three module globals
instead, so a route can only ever reach a `tmp_path` world. If you write
`with TestClient(app) as client:` you will get a slow test that reads live
credentials.

`wire(responses=[...])` returns a client; `client` is `wire(responses=[])`, which
makes any model call raise.

---

## Landmines specific to Phase 3

- **Building `web/dist/` changes `api/main.py`'s import-time behaviour.**
  `mount_frontend()` runs at import and currently returns `False`. The moment
  `npm run build` produces a bundle it will start mounting `/assets` and registering
  an SPA fallback that replaces the handler for *every* `StarletteHTTPException`.
  The Phase 2 tests were written to survive this — they assert on `serves_index`
  directly and never on a non-`/api` 404 through the app — so a green suite after
  your first build is expected, not a sign nothing mounted. **Keep the `/api`
  scoping** if you touch it; without it every frontend typo returns the HTML shell
  with status 200.

- **The error body has three different shapes, and `detail` is not always a string.**
  Verified against the running app. A naive `err.detail` render prints
  `[object Object]` on the first failed form:

  | Source | Status | Body |
  |---|---|---|
  | Pydantic request validation | 422 | `{"detail": [{type, loc, msg, input, ctx}, …]}` — **a list** |
  | `HTTPException` (preconditions, missing rows) | 404/422 | `{"detail": "…"}` |
  | `CopilotError` via `api/errors.py` | mapped | `{"detail": "…", "kind": "MeetingNotFoundError"}` |
  | Unmatched route | 404 | `{"detail": "Not Found"}` |

  **`kind` is not declared in `api/schemas.py`** — it is built inline in
  `handle_copilot_error`. Hand-writing the TypeScript from `api/schemas.py` alone
  will miss it, and `kind` is what lets the UI say "no API key" rather than "request
  failed".

- **The live endpoint list is 14 operations, not the 11 in the plan's table.**
  `GET /api/meetings/{id}/brief/latest` was added in Phase 1 and is not in
  [chunk8_plan.md](chunk8_plan.md). Read `/openapi.json` rather than the plan when
  writing the client. Note also that `app.routes` introspection prints almost
  nothing in FastAPI 0.140 (routers are wrapped in `_IncludedRouter`); that is fine
  and is not a sign nothing registered.

- **`BriefResponse.trace` is `None` for a recalled brief** and populated for a
  generated one. That distinction is deliberate — it is how the UI tells "read from
  storage" from "generated and found nothing" — so the TypeScript type must keep
  `trace` nullable rather than defaulting it to an empty object.

- **The per-meeting lock is held across a whole brief run** — tens of seconds. The UI
  must disable upload controls for a meeting while its brief is generating, rather
  than letting requests queue invisibly. Phase 2 pinned that every index-writing
  route takes the lock, but nothing stops a client from firing them concurrently.

- **`api/schemas.py` re-exports `MeetingBrief` from `core.schema`.** Do not create a
  parallel definition for the frontend's benefit; hand-write the TypeScript from it
  and let it stay the single source.

- **A real `.env` with live API keys sits in the repo root.** Gitignored. Never echo
  it. `tests/conftest.py` neutralises it and `tests/test_conftest_isolation.py`
  guards that — do not weaken it, or the suite reads live credentials and passes for
  the wrong reason.

---

## Environment facts

Phase 1 installed these into `.venv` and they are **still not in
`requirements.txt`** (rewritten in Phase 7):

```
fastapi 0.140.13   uvicorn 0.51.0   python-multipart 0.0.32
```

**Node v24.15.0, npm 11.12.1** are on the machine. `web/` does not exist yet.
`web/vite.config.ts` must pin Vite to **5173** — the CORS allowlist in
`api/main.py` (`DEV_ORIGINS`) already expects it there and nowhere else.

Run the API with:

```bash
.venv/Scripts/python.exe -m uvicorn api.main:app --port 8077 --reload
```

Interactive docs at `/docs`, machine-readable spec at `/openapi.json`. Port 8077 is
arbitrary — it is what Phases 1–2 used.

---

## Verification baseline

```bash
.venv/Scripts/python.exe -m pytest
```

```bash
.venv/Scripts/python.exe -m ruff check core/ tests/ agents/ scripts/ api/
```

**437 tests pass** (~54s, no network, no model downloads) and ruff is clean. The API
tests add ~23s, spread evenly at ~0.15s each building a real SQLite file and FAISS
index per test — that is expected, not a hot spot. `app.py` is still outside the ruff
scope and is deleted in Phase 7 rather than fixed.

Phase 2's headline assertions were mutation-tested rather than trusted: reordering
the status table, dropping the Q&A `and run.error is None`, and removing the upload
loop's lock each produce a red test. If you change any of those three behaviours
deliberately, expect a specific failure and not a vague one.

---

## Suggested skills for the next session

- **`artifact-design`** — read it *before* writing any component. The user's brief is
  "looks like the ChatGPT website, clean and simple, no emojis but clean symbols".
  Calibrate against that rather than reaching for the gradients and shadow stacks the
  old `app.py` used.

- **`run`** — Phases 3–6. Drive the Vite dev server through the Browser pane and
  screenshot it; do not ask the user to check manually.

- **`dataviz`** — Phase 5 only, if the trace timeline grows anything chart-shaped
  (per-specialist hit/neighbour counts are the obvious candidate). Read it before
  choosing colours, not after.

- **`review`** — worth running at the Phase 6 boundary, before Phase 7's deletions
  make the diff large.

- **`tdd`** — only if you extend the API. The frontend has no test harness yet and
  the plan does not ask for one.

---

## Prompt for the next session

> Continue Chunk 8 of the LangGraph overhaul of `D:\hackathon\intelligence_copilot`,
> on branch `feat/react-frontend`. Read `handoffs/chunk8_part2_implemented.md` first,
> then `handoffs/chunk8_plan.md` for the phase plan.
>
> Phases 1 and 2 are done, committed at `b60a79f` and pushed. 437 tests pass, ruff
> clean. **Phase 3 is next: the React shell** — Vite, React 19, TS, Tailwind v4,
> `lucide-react`, a hand-written typed API client, and layout only (sidebar, centred
> content column, light/dark, health status line).
>
> Write the API client against `/openapi.json` rather than the plan's endpoint table
> — there are 14 operations, not 11 — and handle the three error body shapes the
> handoff documents.
>
> Ask before making any live LLM call; none has been made in this entire overhaul and
> it spends real tokens.
>
> Use `.venv/Scripts/python.exe`, not a bare `python`. Keep going phase by phase and
> commit at each boundary; do not attempt the rest of the chunk in one pass.
