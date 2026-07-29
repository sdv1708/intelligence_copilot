# Handoff — Chunk 8 Phase 4 complete, resume at Phase 5

**Date:** 2026-07-29
**Branch:** `feat/react-frontend`, pushed and in sync with `origin/feat/react-frontend`
**Status:** Phases 1–4 of 7 complete. Working tree clean at `a25ec63`.

Read these first; none of their content is repeated here:

- **[handoffs/chunk8_plan.md](chunk8_plan.md)** — the seven-phase plan. Still the
  spec. Its endpoint table is stale; `web/src/api/client.ts` is the accurate list.
- **[handoffs/chunk8_part3_implemented.md](chunk8_part3_implemented.md)** — the
  shell, the palette, the dev-proxy error body, and the `.gitignore` and
  `web/dist/` landmines. **All of those still stand.** Only the parts Phase 4
  changed are restated below.
- **[handoffs/chunk8_part1_implemented.md](chunk8_part1_implemented.md)** — what
  the real database holds. Phase 4 consumed most of its design input; what
  remains relevant to Phase 5 is that four of five meetings have empty `tags`
  and the fifth has a typo, and that one material is 268,347 characters.
- **`git show a25ec63`** — what Phase 4 delivered and why. The commit message
  carries the reasoning; this document carries what is still ahead.

---

## The decisions the user made this session

- **Push the branch.** Done. `main` is still untouched at `72bd17f` and the
  standing decision from Phase 3 holds: **do not merge without asking again.**
- Nothing else was decided. The live-LLM question below was not put to them,
  because Phase 4 never needed to.

## The question that is now due

**No live LLM call has been made in any chunk of this overhaul.** Phase 4 made
none — it calls nine of the client's fourteen operations and not one of them
reaches a provider. The five that remain are exactly the five that do:
`generateBrief`, `listBriefs`, `getLatestBrief`, `getBrief`, `askQuestion`.

`getBrief` and `listBriefs` read stored rows and are free. **`generateBrief` is
not**, and Phase 5 cannot be called done without running it at least once. It
spends real tokens against the Gemini key in `.env`. **Ask before spending
them.** The health endpoint confirms the key is present and the supervisor is
on, so it will work — that is the point.

---

## What Phase 4 built, in one paragraph

Eight new source files under `web/src/`. `format.ts` (display helpers),
`hooks/useMeetingTasks.ts` (the per-meeting busy map), and six components:
`controls.tsx` (`Button`, `ErrorNote`, `Field`, `INPUT`), `MeetingList`,
`NewMeeting`, `MeetingPanel`, `Uploader`, `MaterialsList`. `App.tsx` gained a
three-way `View` union and `Sidebar` lost its placeholder. Read the commit.

## What Phase 5 can build on

- **`useMeetingTasks.run(meetingId, task)` is the thing to wrap
  `generateBrief` in.** It already disables every write control on that meeting,
  shows "locked until it finishes" in the panel and spins the sidebar row. It
  was built for the brief and exercised with a 189k-character upload; the brief
  is the case it exists for. Do not add a second busy mechanism.
- **`controls.tsx` is the shared vocabulary.** `ErrorNote` already withholds the
  retry for the kinds retrying cannot fix, so call sites pass `onRetry`
  unconditionally rather than duplicating the condition.
- **The two-step delete pattern** (`confirming` state, danger button, a sentence
  naming what goes) is in both `MeetingPanel` and `MaterialsList`. Reuse it if
  briefs become deletable.
- **`MeetingPanel` is where the brief goes**, as a section below Documents. It
  already holds the meeting request, the materials request and `tasks`.

---

## Landmines specific to Phase 5

- **`useRequest` drops to `loading` while it refetches.** Any component that
  renders a skeleton for `loading` will unmount its children on every reload —
  `MeetingPanel.refresh` deliberately reloads only the materials list for this
  reason, or the upload report would vanish as it is being read. A brief view
  that reloads history after a generation will hit exactly the same thing.

- **Do not use `useRequest` for `generateBrief`.** It runs on mount and on
  `reload`; a POST that costs money and tens of seconds must be button-driven.
  `useState` plus `tasks.run` is the shape.

- **`BriefResponse.trace` is null for a stored brief and populated for a fresh
  one, and that distinction is the feature.** Defaulting it to an empty trace
  collapses "recalled from storage" into "generated and found nothing". The
  plan's headline for Phase 5 — the piece Streamlit could not show — is only
  visible on a freshly generated brief, which is the second reason a live call
  is unavoidable.

- **`ok: true` with a non-null `warning` means the brief generated and then
  failed to store.** Read both fields. Rendering only `ok` throws away the
  warning; rendering only `warning` throws away a usable brief.

- **`QaResponse` is the opposite asymmetry.** An answer with an `error` is
  `ok: false`, and its `answer` text is the "nothing retrieved" boilerplate.
  Showing it as an answer disguises a broken index as a polite non-answer.
  `api/translate.py` is where both asymmetries are decided; the tests in
  `tests/test_api.py` pin them.

- **The per-meeting lock is held for the whole brief run — tens of seconds.**
  Handled, but only if the brief goes through `tasks.run`. See above.

- **`web/dist/` is current as of `a25ec63`** and `mount_frontend()` returns
  `True`, so FastAPI serves the Phase 4 bundle at `/` on 8077. **Rebuild it
  after any frontend change**, or 8077 silently serves a stale UI while 5173
  serves the real one — a confusing half-hour. `npm run build --prefix web`.

- **The root `.gitignore` still has unanchored `lib/`.** A `web/src/lib/`
  directory would be silently untracked. Phase 4 stuck to `src/components/` and
  `src/hooks/` for this reason.

## Things earlier handoffs got wrong

- **`UnsupportedFileTypeError` (415) and `EmptyDocumentError` (422) do not reach
  the UI on the upload path.** Every handoff since Phase 1 said Phase 4 would
  see them. It does not: `parse_file` returns `("", "unknown")` for an
  unrecognised extension rather than raising, and `ingest_material` catches
  `CopilotError` itself and returns `{"success": False, "error": ...}`. Both
  arrive as a per-file string inside a **200**. Verified live with a `.xyz`
  file — the UI showed "No readable text could be extracted from 'notes.xyz'".
  The kind that genuinely matters to the UI is **`MeetingNotFoundError`**, from
  a meeting deleted in another tab, and `MeetingPanel` handles it with a
  no-retry error and a way back to the status view.

- **The `StatusPanel` "Not built yet" block was trimmed, not deleted.** Phase 3's
  handoff said it goes at Phase 4. Only its meetings line was true to remove;
  briefs and Q&A genuinely are not built and deleting the section would have
  removed accurate information. **It goes entirely at the end of Phase 6.**

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

**437 tests pass** (~39s), ruff is clean, the frontend typechecks and builds.
`web/` still has no test harness and the plan does not ask for one.

Note that Phase 3's handoff gave the typecheck as `npx tsc -b --prefix web`.
That command does not work: `--prefix` is an npm flag, and from the repo root
`npx tsc` cannot see the TypeScript in `web/node_modules`, so it downloads an
unrelated `tsc` package from the registry and fails with a message about not
being the compiler you are looking for. Use the npm script above, or `npx tsc -b`
from inside `web/`.

### How Phase 4 was verified

Against the real `data/briefs.db`, through the Browser pane: the five real
meetings listed with `"Q4 "` and `"check in "` trimmed at display; a meeting
created with an empty attendee dropped; two files dropped at once with one
failing and both reported; text pasted; a material deleted; a 189k-character
upload watched mid-flight to confirm every write control was disabled; then the
whole test meeting deleted. **The database is back exactly as it was — five
meetings, nothing added.** No console errors, no horizontal overflow at 375px,
the mobile drawer closing on selection, light and dark both looked at.

### Browser-pane notes, corrected from Phase 3

- **Screenshots worked this session.** Phase 3's handoff said they always timed
  out; that was that session, not a standing condition. They do fail with "the
  page is not compositing frames" whenever the pane is not displayed, so if one
  times out, fall back to `read_page` and carry on rather than debugging it.
- **`computer` clicks by `ref` were not used** — `javascript_tool` with
  `element.click()` was, and it worked for every control including the ones
  Phase 3 reported as unclickable. Keep using it.
- **New, and it will waste your time once: reading the DOM in the same
  `javascript_tool` call as a `.click()` gives you the *pre-render* DOM.** React
  has not re-rendered yet. The drawer looked stuck open and the main column
  looked unchanged; a second call showed both correct. Split the click and the
  assertion into two calls.
- **Drag-and-drop is testable without a real pointer**: build a `DataTransfer`,
  `items.add(new File([...], name, {type}))`, and dispatch
  `new DragEvent('drop', {bubbles: true, dataTransfer})` at the dropzone. That
  is how the partial-failure path above was exercised.

---

## Suggested skills for the next session

- **`run`** — Phases 5–6. Read the Browser-pane notes above first.
- **`dataviz`** — Phase 5, before choosing any colour for the trace. The
  per-specialist hit/neighbour counts are the chart-shaped thing, and `hits` and
  `neighbours` must not be summed or stacked as if they were the same quantity.
- **`artifact-design`** — the brief is a document, not a dashboard. The palette
  and type scale are in `web/src/index.css`; extend, do not restart.
- **`review`** — at the Phase 6 boundary, before Phase 7's deletions make the
  diff large.
- **`handoff`** — at the next phase boundary. This project keeps handoffs in
  `handoffs/` and commits them, not in the OS temp directory.

---

## Prompt for the next session

> Continue Chunk 8 of the LangGraph overhaul of `D:\hackathon\intelligence_copilot`,
> on branch `feat/react-frontend`. Read `handoffs/chunk8_part4_implemented.md`
> first, then `handoffs/chunk8_plan.md` for the phase plan.
>
> Phases 1–4 are done, committed at `a25ec63` and pushed. 437 tests pass, ruff
> clean, frontend typechecks and builds. **Phase 5 is next: the brief and its
> trace** — recap, action items, topics, agenda and evidence, plus the piece
> Streamlit could not show: the plan, per-specialist findings with hit and
> neighbour counts, failed enquiries and the node timeline. History dropdown,
> JSON and Markdown export.
>
> Wrap `generateBrief` in `useMeetingTasks.run` — the server holds the meeting's
> lock for the whole run and that hook already disables every write control.
> Do not use `useRequest` for it; it is a button-driven POST that costs money.
> `trace` is null for a stored brief and populated for a fresh one — keep that
> distinction visible rather than defaulting it.
>
> **Ask before making the live LLM call.** None has been made in this entire
> overhaul, and Phase 5 is where it stops being avoidable — a stored brief has
> no trace, so the headline feature cannot be seen without generating one.
>
> Do not merge to `main`; the user is keeping it untouched until the overhaul is
> finished. Rebuild `web/dist` after frontend changes or FastAPI on 8077 serves
> a stale bundle. Use `.venv/Scripts/python.exe`, not a bare `python`. Keep
> going phase by phase and commit at each boundary.
