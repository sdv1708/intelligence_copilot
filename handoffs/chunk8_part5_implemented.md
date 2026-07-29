# Handoff — Chunk 8 Phase 5 complete, resume at Phase 6

**Date:** 2026-07-29
**Branch:** `feat/react-frontend`, pushed and in sync with `origin/feat/react-frontend`
**Status:** Phases 1–5 of 7 complete. Working tree clean at `3674b6e`.

Read these first; none of their content is repeated here:

- **[handoffs/chunk8_plan.md](chunk8_plan.md)** — the seven-phase plan. Still the
  spec. Its endpoint table is stale; `web/src/api/client.ts` is the accurate list.
- **[handoffs/chunk8_part4_implemented.md](chunk8_part4_implemented.md)** — the
  per-meeting lock, the `useRequest` reload landmine, the `web/dist/` and
  unanchored-`lib/` landmines, and the drag-and-drop testing recipe. **All of
  those still stand.** Only what Phase 5 changed or disproved is restated below.
- **`git show 3674b6e`** — what Phase 5 delivered and why. The commit message
  carries the reasoning; this document carries what is still ahead.

---

## The decisions the user made this session

- **Push the branch.** Done, including this handoff. `main` is still untouched at
  `72bd17f` and the standing decision holds: **do not merge without asking again.**
- **Make the live call — but on OpenAI, not Gemini.** The user has OpenAI
  credits and asked for those to be spent rather than the Gemini quota. See the
  next section for why that did not happen.

## The question that is now due, again — and the reason it stalled

**No live provider call has succeeded in any chunk of this overhaul.** Phase 5
tried, with permission, and got a 401 in six seconds:

```
OPENAI_API_KEY=your_openai_api_key_here      ← placeholder
ANTHROPIC_API_KEY=your_anthropic_api_key_here ← placeholder
GEMINI_API_KEY=AIzaSyB…oJgQ                   ← the only real key in .env
```

**Do not ask the user to paste a key into the chat.** They put it in `.env`
themselves; you read `/api/health` to confirm it took. The run is then:

```bash
LLM_PROVIDER=openai .venv/Scripts/python.exe -m uvicorn api.main:app --port 8077
```

`core/llm_providers.py:121` builds `ChatOpenAI` and `openai_model` defaults to
`gpt-4o`, so nothing needs writing — only the key.

**`has_api_key` in `/api/health` is a length check, not a validity check.**
`Settings.has_api_key` calls `api_key_for`, which raises only on an *empty*
value. A placeholder passes, and the status view says "API key: Present" for a
key that cannot authenticate. That is why the placeholder survived five phases.
Worth fixing, but it is a `core/config.py` change and Phase 5 did not make it.

**Only two of the fourteen client operations cost money: `generateBrief` and
`askQuestion`.** Phase 4's handoff listed five and then contradicted itself two
sentences later. `listBriefs`, `getBrief` and `getLatestBrief` read stored rows.

---

## What the 401 proved anyway

More than expected, and it is why Phase 6 should not treat a failed live run as
a wasted one. The retrieval half of the graph ran **live against the real
database with real embeddings**, and the failure path rendered exactly as
designed: no brief document, **no export buttons** (there was nothing to
export), the 401 in the critical style rather than the warning style because
`ok` was false, and the trace still rendered — the supervisor falling back to
the standing roster after its own 401, five specialists with genuinely varied
counts (`15/0` for the sweep, `5/5` for action items, `6/3` for decisions), then
`SYNTHESIS — failed`.

Nothing was written: `data/briefs.db` still holds 5 meetings, 10 briefs, 9
materials, exactly as it did at the start of the session.

---

## What Phase 5 built, in one paragraph

Four new source files: `brief.ts` (Markdown/JSON serialisation and the download
helper — pure functions over a `BriefResponse`, plus one DOM call) and three
components, `BriefDocument`, `TraceView`, `BriefPanel`. `MeetingPanel` mounts
`BriefPanel` below Documents, keyed on the meeting. `format.ts` gained
`formatMoment`. `asApiError` moved from four hand-written copies into
`api/errors.ts`. Two server-side fixes went with it, both silent defects — read
the commit.

## What Phase 6 can build on

- **`TraceView` already renders a Q&A trace**, because every block is
  conditional: no plan and no findings means those two sections are skipped and
  the timeline plus the chunk count remain. See the landmine below about its
  header, which is the one part that does not degrade cleanly.
- **`useMeetingTasks.run` is the wrapper for `askQuestion` too.** `api/deps.py`
  takes the same per-meeting lock for a Q&A run as for a brief, because
  `Retriever.recall` backfills the index.
- **`BriefPanel`'s state machine is the shape a Q&A composer wants**: a
  hand-rolled `State` union, a `useRef` token so a slow response cannot land
  after a newer one, and no `useRequest` anywhere near the POST. Copy the
  structure rather than reaching for the hook.
- **`brief.ts`'s `download` and `slug`** are not brief-specific. A Q&A
  transcript export can use both unchanged.
- **The `Note` component in `BriefPanel`** (an info icon plus a sentence) is the
  established way to say something that is not an error. It is duplicated
  nowhere yet; if Q&A needs it, hoist it into `controls.tsx`.

---

## Landmines specific to Phase 6

- **`TraceView`'s header is wrong for a Q&A trace.** `api/translate.py:79`
  builds `Trace(notes=…, chunks=…)` and leaves `plan_source` as `""`, so the
  header renders "Plan source: unknown" — a sentence about planning on a run
  that never planned. Either give the component a mode, or have it omit the
  header when `plan_source` is empty. Do not fix it by making `qa_response`
  invent a plan source.

- **`QaResponse`'s asymmetry is the opposite of a brief's, and both are live.**
  An answer with an `error` is `ok: false`, and its `answer` text is the
  "nothing retrieved" boilerplate — rendering it as an answer disguises a broken
  index as a polite non-answer. A brief with a `warning` may still be `ok: true`.
  `api/translate.py` decides both; `tests/test_api.py` pins both.

- **`provider` is `""` on a recalled brief and will be on any stored read.**
  `api/routes/briefs.py`'s `latest_brief` and `get_brief` never set it — only
  `brief_response` does, from the live run. `BriefPanel` shows the model and not
  the provider for exactly this reason. If Q&A grows a "which model answered
  this" line, check the field is populated before rendering it.

- **The per-meeting lock is held for the whole Q&A run**, same as the brief.
  Handled only if the call goes through `tasks.run`.

- **`StatusPanel`'s "Not built yet" block now has one line left.** Phase 5 removed
  the briefs line. **Delete the whole `<section>` at the end of Phase 6**, not
  the last `<li>` — an empty dashed box is worse than either state.

- **`web/dist/` is current as of `3674b6e`** and gitignored (`web/.gitignore:2`),
  so it is a purely local artefact. FastAPI on 8077 serves whatever was last
  built. **Rebuild after any frontend change** or 8077 silently serves a stale UI
  while 5173 serves the real one. `npm run build --prefix web`.

- **The root `.gitignore` still has unanchored `lib/`.** A `web/src/lib/`
  directory would be silently untracked. Phase 5 put `brief.ts` at the `src/`
  root for this reason.

## Things earlier handoffs got wrong

- **Phase 4's handoff said `useMeetingTasks.run` "was built for the brief and
  the brief is the case it exists for".** True, and it works — but note that the
  6-second 401 run was too fast to observe the disabled controls, so **the lock
  UI has still only ever been watched during a long upload, never during a long
  brief.** Watch for it on the first successful live run.

- **Phase 4's handoff said screenshots "worked this session".** They worked for
  the first half of this session and then began failing with "the page is not
  compositing frames" for the rest of it, with no change in what was being done.
  Treat it as intermittent: if one times out, fall back to `read_page` or
  `javascript_tool` and carry on. Do not debug it.

---

## Two techniques worth reusing

**Exercise a costly POST without paying for it.** Phase 5 verified the whole
trace rendering — plan, per-specialist bars, failed enquiries, node timeline —
against a *real* `Trace` from the *real* graph over a *real* FAISS index, with
`HashingEmbedder` and a scripted model in place of the provider. Build the
response server-side with the `tests/agentworld.py` fixtures through
`TestClient` (a throwaway script in the scratchpad, not in the repo), then in the
browser patch `window.fetch` to answer that one route from it and click the
button. `askQuestion` is the same shape.

Two things that matter: pass a **real transcript** from `sample_data/` as
`build_world(text=…)`, because the six-paragraph default fixture makes every
specialist report "5 hits, 0 neighbours" and tells you nothing about whether the
two counts render distinguishably. And keep the real `api/translate.py` in the
path — a hand-written JSON fixture would not have caught the `stored_at` bug.

**`javascript_tool` evaluates in a persistent scope.** A second call declaring
the same `const` fails with "Identifier 'm' has already been declared", which
reads like a page error and is not. Wrap every snippet in an IIFE. This is on
top of Phase 4's note that reading the DOM in the same call as a `.click()`
gives you the pre-render DOM — both are still true, and they compound.

---

## Environment facts

Unchanged from Phase 3 — Node v24.15.0, npm 11.12.1, the same resolved frontend
versions, the same `@types/node` requirement, the same missing Python pins
(`fastapi`, `uvicorn`, `python-multipart`, rewritten in Phase 7). Vite is still
pinned to 5173 with `strictPort` because `DEV_ORIGINS` names that port.

Run both halves:

```bash
.venv/Scripts/python.exe -m uvicorn api.main:app --port 8077 --reload
```

```bash
npm run dev --prefix web
```

`.claude/launch.json`'s `web` entry works with `preview_start {name: "web"}`.
Its `copilot` entry still launches Streamlit and goes in Phase 7.

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

**437 tests pass** (~41s), ruff is clean, the frontend typechecks and builds.
Phase 5 added assertions to two existing tests rather than new test functions,
so the count is unchanged from Phase 4.

`web/` still has no test harness and the plan does not ask for one. If Phase 6
or 7 adds one, **`brief.ts` is the file to point it at** — `briefToMarkdown` and
`briefFilename` are pure functions over a `BriefResponse` with no DOM in them,
and the empty-section behaviour is the kind of thing that regresses quietly.

### How Phase 5 was verified

Against the real `data/briefs.db`, through the Browser pane: the three stored
briefs on "check in" listed and switched between; both exports read back out of
the blob rather than downloaded (patch `URL.createObjectURL` and
`HTMLAnchorElement.prototype.click`, then restore); the empty-section wording
checked in the Markdown; the trace exercised as described above; no console
errors, no horizontal overflow at 375px, light and dark both looked at. **The
database is exactly as it was — five meetings, ten briefs, nine materials.**

---

## Suggested skills for the next session

- **`run`** — Phase 6. Read the Browser-pane notes above first.
- **`review`** — at the Phase 6 boundary, before Phase 7's deletions make the
  diff large. This was suggested for Phase 5 and not taken; the diff is now two
  phases wide.
- **`handoff`** — at the next phase boundary. This project keeps handoffs in
  `handoffs/` and commits them, not in the OS temp directory.

---

## Prompt for the next session

> Continue Chunk 8 of the LangGraph overhaul of `D:\hackathon\intelligence_copilot`,
> on branch `feat/react-frontend`. Read `handoffs/chunk8_part5_implemented.md`
> first, then `handoffs/chunk8_plan.md` for the phase plan.
>
> Phases 1–5 are done, committed at `3674b6e` and pushed. 437 tests pass, ruff
> clean, frontend typechecks and builds. **Phase 6 is next: Q&A** — a
> composer-style input, a conversation thread, source citations, and a
> per-answer trace.
>
> Wrap `askQuestion` in `useMeetingTasks.run`; the server takes the same
> per-meeting lock as for a brief. Copy `BriefPanel`'s hand-rolled state machine
> rather than using `useRequest` for the POST. An answer with an `error` is
> `ok: false` and its text is boilerplate — do not render it as an answer.
> `TraceView` mostly works for a Q&A trace already, but its header claims a plan
> source on a run that never planned; fix that in the component, not by making
> `qa_response` invent one.
>
> **The live provider call is still owed and is now blocked on a key.** Phase 5
> had permission and got a 401: `OPENAI_API_KEY` and `ANTHROPIC_API_KEY` in
> `.env` are both `your_..._here` placeholders, and only `GEMINI_API_KEY` is
> real. Ask the user to put their own key in `.env` — do not ask them to paste it
> into the chat — then confirm with `/api/health` and run. `has_api_key` there is
> a length check and will say "Present" for a placeholder, so it is not proof.
>
> At the end of Phase 6, delete the whole "Not built yet" section from
> `StatusPanel`, not just its last line.
>
> Do not merge to `main`; the user is keeping it untouched until the overhaul is
> finished. Rebuild `web/dist` after frontend changes or FastAPI on 8077 serves
> a stale bundle. Use `.venv/Scripts/python.exe`, not a bare `python`. Keep
> going phase by phase and commit at each boundary.
