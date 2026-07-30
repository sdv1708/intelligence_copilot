# Handoff — Chunk 8 Phase 6 complete, resume at Phase 7

**Date:** 2026-07-29
**Branch:** `feat/react-frontend`, pushed and in sync with `origin/feat/react-frontend`
**Status:** Phases 1–6 of 7 complete. Working tree clean at `0a787c9`.

Read these first; none of their content is repeated here:

- **[handoffs/chunk8_plan.md](chunk8_plan.md)** — the seven-phase plan. Phase 7 is
  the only one left. Its endpoint table is stale; `web/src/api/client.ts` is the
  accurate list. **One line of its Phase 7 description is wrong** — see the first
  landmine below.
- **[handoffs/chunk8_part5_implemented.md](chunk8_part5_implemented.md)** — the
  per-meeting lock, the `useRequest` reload landmine, the `web/dist/` and
  unanchored-`lib/` landmines, and the two techniques for exercising a costly
  POST. **All of those still stand**, and the POST technique was used again this
  session. Only what Phase 6 changed or disproved is restated here.
- **`git show 0a787c9`** — what Phase 6 delivered and why. The commit message
  carries the reasoning.

---

## The decisions the user made this session

- **Implement Phase 6, commit, push, write this handoff.** All done.
- **`main` is still untouched** at `72bd17f`. The standing decision holds: **do
  not merge without asking again.**

## The question that is still due

**No live provider call has been made in any chunk of this overhaul.** Phase 6
did not need one — the whole Q&A surface was verified against responses built by
the real graph with a scripted model — so this is now owed for the third phase
running.

It is blocked on a key, not on permission. `.env` holds:

```
OPENAI_API_KEY=your_openai_api_key_here      ← placeholder
ANTHROPIC_API_KEY=your_anthropic_api_key_here ← placeholder
GEMINI_API_KEY=AIzaSyB…oJgQ                   ← the only real key, and it 401s
```

**Do not ask the user to paste a key into the chat.** They put it in `.env`
themselves; you read `/api/health` to confirm it took. Then:

```bash
LLM_PROVIDER=openai .venv/Scripts/python.exe -m uvicorn api.main:app --port 8077
```

`has_api_key` in `/api/health` is a **length check, not a validity check** —
`Settings.has_api_key` calls `api_key_for`, which raises only on an *empty*
value, so a placeholder renders as "API key: Present". Six phases have now
survived on that. Fixing it is a `core/config.py` change and remains unmade;
Phase 7 is a reasonable place for it but the plan does not ask.

Only `generateBrief` and `askQuestion` cost money. The other twelve client
operations read stored rows.

---

## What Phase 6 built

Read the commit. The one-paragraph version: `QaPanel.tsx` (the thread, composer,
grouped citations and a folded per-answer trace), `TraceView`'s header made
conditional so a Q&A trace stops claiming a plan source, `Note` hoisted into
`controls.tsx` and `Alert` split out of `ErrorNote`, `StatusPanel`'s "Not built
yet" section deleted, and two assertions added to `tests/test_api.py`.

Test count is **unchanged at 437** — Phase 6 added assertions to existing tests
rather than new test functions, same as Phase 5.

---

## Landmines specific to Phase 7

- **"Add a run script that serves the built frontend from FastAPI on one port"
  is half done already, and the half that exists is not the script.**
  `api/main.py:89` `mount_frontend()` already mounts `web/dist` and installs the
  SPA fallback, and it is **called at import time** (`api/main.py:128`), so
  whether the bundle is served is decided when the module is imported, not when
  a request arrives. Phase 7 needs the *wrapper* — build the frontend, then run
  uvicorn — not the serving. Do not rewrite `mount_frontend`; `serves_index` is
  pinned by `tests/test_api.py` and the scoping rule in its docstring is load
  bearing.

- **Deleting `app.py` breaks no code but strands eight pieces of prose.** The
  facade it calls must **stay** — `api/` is its only caller now. What needs
  rewording, not removing:

  | File | Lines |
  |---|---|
  | `agents/__init__.py` | 5, 10 |
  | `agents/copilot_orchestrator.py` | 3, 16, 108, 221 |
  | `core/prompts.py` | 118 |
  | `tests/test_orchestrator.py` | 1, 203 |

  Plus two configs that would break outright: `.claude/launch.json`'s `copilot`
  entry (launches Streamlit on 8501) and `.devcontainer/devcontainer.json` lines
  9, 20 and 22 — line 20 `pip3 install --user streamlit` unconditionally, line 22
  runs `streamlit run app.py` as the devcontainer's server command.

- **`requirements.txt` is worse than "one stale pin".** All fourteen pins are
  behind the venv, four packages the code imports are missing entirely, and two
  pinned packages are imported nowhere at all (verified by grep across the repo).

  | | Pinned | Installed |
  |---|---|---|
  | `langchain` | 0.3.7 | **1.0.5** |
  | `langchain-core` | — | 1.0.4 |
  | `langgraph` | **missing** | 1.0.2 |
  | `langchain-google-genai` | 2.0.5 | 3.0.1 |
  | `langchain-openai` | 0.2.9 | 1.0.2 |
  | `langchain-anthropic` | 0.3.0 | 1.0.2 |
  | `fastapi` | **missing** | 0.140.13 |
  | `uvicorn` | **missing** | 0.51.0 |
  | `python-multipart` | **missing** | 0.0.32 |
  | `pydantic` | 2.9.0 | 2.12.4 |
  | `faiss-cpu` | 1.9.0.post1 | 1.12.0 |
  | `sentence-transformers` | 3.3.0 | 5.1.2 |
  | `pypdf` | 5.1.0 | 6.1.3 |
  | `python-docx` | 1.1.2 | 1.2.0 |
  | `python-pptx` | 1.0.2 | 1.0.2 |
  | `python-dotenv` | 1.0.1 | 1.2.1 |
  | `streamlit` | 1.39.0 | goes with `app.py` |
  | `sqlmodel` | 0.0.22 | **imported nowhere — delete** |
  | `pandas` | 2.2.3 | **imported nowhere — delete** |

  Not pinned anywhere and needed to run the suite: `pytest` 9.1.1, `ruff` 0.16.0,
  `httpx` 0.28.1 (`TestClient` requires it). A `requirements-dev.txt` is the
  obvious split but the plan does not ask for one.

- **`README.md` is 488 lines and the rot is not confined to the two spots the
  plan names.** Confirmed stale: line 161 `streamlit run app.py` as *the* way to
  run it; line 313 listing `app.py` as the entry point in the project tree; lines
  403–408 documenting `[INFO]`/`[OK]` log prefixes and `[IngestionTool]`/
  `[RecallTool]` class names that no longer exist; lines 412–422 a "Streamlit
  Cloud" deployment section; lines 345–368 an "API Reference" that documents
  orchestrator *methods* rather than the fourteen HTTP endpoints that are now the
  actual API; lines 54–76 "Technical Stack" with no React, FastAPI or LangGraph
  in it.

- **Two test warnings are not ours and should not be chased.**
  `StarletteDeprecationWarning: Using httpx with starlette.testclient is
  deprecated; install httpx2` comes from `fastapi/testclient.py:1` on import.
  `LangGraphDeprecatedSinceV10: AgentStatePydantic has been moved` is raised from
  inside langgraph during `test_graph.py`; **nothing in this repo imports
  `AgentStatePydantic`** (grepped). Both are dependency-internal.

- **`web/dist/` is current as of `0a787c9`** and gitignored (`web/.gitignore:2`),
  so it is purely local. FastAPI on 8077 serves whatever was last built.
  **Rebuild after any frontend change**: `npm run build --prefix web`.

- **The root `.gitignore` still has unanchored `lib/`** (`.gitignore:21`), so a
  `web/src/lib/` directory would be silently untracked. `dist/` at line 17 is
  likewise unanchored. Phase 5 put `brief.ts` at the `src/` root for this reason
  and Phase 6 kept everything in `components/`.

---

## Browser-pane notes, updated

The Phase 5 handoff said screenshots were intermittent. **This session they
failed on every single attempt**, from the first, with `the Browser pane is not
displayed, so the page is not compositing frames`. Everything below was verified
without one. Do not debug it; work through `read_page` and `javascript_tool`.

Three things that cost time and will cost it again:

- **`read_page {filter: "interactive"}` did not list the composer's `<textarea>`
  or its submit button**, though both were plainly interactive and on screen.
  `filter: "all"` scoped to the `main` ref did list them. `find` is unusable
  until a `read_page` tree is cached, and every reload invalidates the ref
  numbers.

- **HMR leaves stale computed styles on nodes whose className it changed.** After
  editing one `text-faint` to `text-muted`, `getComputedStyle` on that node kept
  returning the *old* token's colour, while a freshly created `<span>` with the
  same class appended to the *same parent* returned the correct one. This reads
  exactly like a contrast bug in the code and is not one. **Measure colour only
  after a full reload.**

- **The pane's light/dark emulation stopped taking effect partway through.**
  `resize_window {colorScheme: "light"}` made `matchMedia` report light while
  `.bg-paper` stayed at `rgb(26,27,28)`, and removing the app's own `.dark` class
  did not change the paint either. Only one scheme got measured as a result.
  Phase 6 introduces no new colour tokens — every class it uses already appears
  in `MaterialsList`, `BriefDocument` or `BriefPanel` — so this was accepted
  rather than fought. If Phase 7 needs a real two-theme check, reload between
  scheme changes and verify the paint before trusting `matchMedia`.

Still true from Phase 5, and they compound: `javascript_tool` evaluates in a
**persistent scope** (wrap every snippet in an IIFE or a repeated `const` fails
with "already been declared"), and **reading the DOM in the same call as a
`.click()` gives you the pre-render DOM**.

One new one: **editing any component file resets `App`'s view to `status`** via
the HMR remount, which also wipes the Q&A thread — that is by design, the thread
is local state. Re-select the meeting after every edit.

---

## Things earlier handoffs got wrong or left open

- **Phase 5's handoff flagged that "the lock UI has only ever been watched during
  a long upload, never during a long brief."** Now watched, on a 12-second
  scripted Q&A run: the uploader dropzone, "Paste text instead", both per-file
  delete buttons, "Generate again" and "Ask" all disable together, and the
  Documents heading shows "Working — this meeting is locked until it finishes".
  The composer's textarea deliberately stays enabled so the next question can be
  typed while one is in flight; only the send is blocked.

- **Phase 5's handoff said `brief.ts`'s `download` and `slug` would suit a Q&A
  transcript export.** They would, and they are still unused by Q&A — the plan
  asks for "composer, thread, citations, trace" and Phase 6 did not widen it.
  If the user wants a thread export, both functions take it unchanged.

- **`web/` still has no test harness** and the plan does not ask for one. There
  are now *two* files of pure functions worth pointing one at: `brief.ts`
  (`briefToMarkdown`, `briefFilename`) and `QaPanel.tsx`'s `citations`, which
  groups source refs and handles the deleted-material and malformed-ref
  fallbacks. `citations` is module-private and would need exporting or moving.

---

## Environment facts

Unchanged from Phase 3 — Node v24.15.0, npm 11.12.1, the same resolved frontend
versions, the same `@types/node` requirement. Vite is still pinned to 5173 with
`strictPort` because `DEV_ORIGINS` (`api/main.py:33`) names that port.

Run both halves:

```bash
.venv/Scripts/python.exe -m uvicorn api.main:app --port 8077 --reload
```

```bash
npm run dev --prefix web
```

`.claude/launch.json`'s `web` entry works with `preview_start {name: "web"}`. Its
`copilot` entry still launches Streamlit and goes in Phase 7. The backend takes
**about 20 seconds** to become reachable — it builds the chat model, then loads
the embedding model — so the first `/api/health` after starting it will 502 and
that is not a fault.

To stop a backend you started in the background:

```bash
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8077 -State Listen | Select-Object -ExpandProperty OwningProcess | ForEach-Object { Stop-Process -Id $_ -Force }"
```

---

## Verification baseline

```bash
.venv/Scripts/python.exe -m pytest
```

```bash
.venv/Scripts/python.exe -m ruff check core/ tests/ agents/ scripts/ api/
```

```bash
npm run typecheck --prefix web
```

```bash
npm run build --prefix web
```

**437 tests pass** (~39s), ruff is clean, the frontend typechecks and builds.

Note that `pytest -q` and `pytest -q | grep passed` **do not print a summary
line** in this environment — the count only appears without `-q`.

### How Phase 6 was verified

Against the real `data/briefs.db` through the Browser pane, on the "check in"
meeting (two indexed transcripts). The costly POST was exercised with Phase 5's
technique — responses built server-side by the real graph over a real FAISS index
through the real `api/translate.py`, using `HashingEmbedder` and a scripted
model, then `window.fetch` patched in the browser to answer that one route.
Throwaway scripts in the scratchpad, not in the repo.

Four response shapes, all produced by the real graph rather than hand-written:
an answer citing 12 sources across 36 retrieved chunks; an empty search
(`ok: true`, 0 chunks, the boilerplate); an in-band retrieval failure
(`ok: false` at HTTP 200); and a transport failure. Plus a variant carrying a
deleted material's id and a malformed ref, to see the citation fallbacks.

Also checked: Enter-to-send and the composer clearing; a retry replacing its turn
in place rather than appending; the Q&A trace rendering with **no** plan-source
header; the brief's trace still rendering **with** its header (the regression
risk of the `TraceView` edit, checked against a real `BriefResponse` whose
`plan_source` is `"default"`); no console errors on a clean load; no horizontal
overflow at 375px with an eleven-chunk citation chip.

**The database is exactly as it was — 5 meetings, 10 briefs, 9 materials, 872
chunks.** Nothing in Phase 6 writes rows, and no patched request reached the
server.

---

## Suggested skills for the next session

- **`review`** — **before** Phase 7. This was suggested at the Phase 5 boundary
  and at the Phase 4 boundary and taken at neither; the diff is now three phases
  wide and Phase 7 is mostly deletions, which will make it wider and harder to
  read.
- **`run`** — Phase 7, to check the single-port build actually serves. Read the
  Browser-pane notes above first.
- **`handoff`** — at the end, but Phase 7 already owes
  `handoffs/chunk8_implemented.md` as a deliverable, so fold the two together.

---

## Prompt for the next session

> Continue Chunk 8 of the LangGraph overhaul of `D:\hackathon\intelligence_copilot`,
> on branch `feat/react-frontend`. Read `handoffs/chunk8_part6_implemented.md`
> first, then `handoffs/chunk8_plan.md` for the phase plan.
>
> Phases 1–6 are done, committed at `0a787c9` and pushed. 437 tests pass, ruff
> clean, frontend typechecks and builds. **Phase 7 is the last one: cleanup.**
> Delete `app.py`, rewrite `requirements.txt`, fix `README.md`, add a run script
> that builds the frontend and serves it from FastAPI on one port, and write
> `handoffs/chunk8_implemented.md`.
>
> The handoff has the specifics you will otherwise rediscover: FastAPI **already**
> serves `web/dist` (`api/main.py:89`, called at import time), so Phase 7 needs
> the wrapper script and not the serving; `app.py`'s deletion strands prose in
> six source files plus `.claude/launch.json` and `.devcontainer/devcontainer.json`,
> but the `CopilotOrchestrator` facade itself must stay because `api/` calls it;
> `requirements.txt` has four missing packages and two — `sqlmodel` and `pandas` —
> that nothing imports; and `README.md`'s rot goes well beyond the two spots the
> plan names.
>
> **The live provider call is still owed and is still blocked on a key.**
> `OPENAI_API_KEY` and `ANTHROPIC_API_KEY` in `.env` are both `your_..._here`
> placeholders. Ask the user to put their own key in `.env` — do not ask them to
> paste it into the chat — then confirm with `/api/health` and run. `has_api_key`
> there is a length check and says "Present" for a placeholder, so it is not
> proof.
>
> Consider running `review` before starting: the diff is three phases wide and
> Phase 7 is mostly deletions.
>
> Do not merge to `main`; the user is keeping it untouched until the overhaul is
> finished. Rebuild `web/dist` after frontend changes or FastAPI on 8077 serves a
> stale bundle. Use `.venv/Scripts/python.exe`, not a bare `python`. Screenshots
> did not work at all last session — use `read_page` and `javascript_tool`.
