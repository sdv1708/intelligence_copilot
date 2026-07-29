# Handoff — Chunk 8 Phase 3 complete, resume at Phase 4

**Date:** 2026-07-29
**Branch:** `feat/react-frontend`, pushed and in sync with `origin/feat/react-frontend`
**Status:** Phases 1–3 of 7 complete. Working tree clean at `6839e3c`.

Read these first; none of their content is repeated here:

- **[handoffs/chunk8_plan.md](chunk8_plan.md)** — the seven-phase plan. Still the
  spec for the rest of the work. Its endpoint table is stale (11 rows, 14 live
  operations); the client in `web/src/api/client.ts` is now the accurate list.
- **[handoffs/chunk8_part1_implemented.md](chunk8_part1_implemented.md)** — what the
  real database holds. **Still entirely design input for Phase 4**: trailing spaces
  in titles (`"Q4 "`), `tags` empty on four of five meetings and a typo on the
  fifth, informal attendees (`"sanj"`), a 268,347-character material, null
  `filename`/`media_type` on real rows.
- **[handoffs/chunk8_part2_implemented.md](chunk8_part2_implemented.md)** — how
  `tests/test_api.py` is wired, and why the `TestClient` is never a context manager.
- **`git show 6839e3c`** — what Phase 3 delivered and the reasoning behind the
  non-obvious parts (the dev-proxy error body, `@theme inline`, the three-state
  theme).

---

## The decision the user made this session

Asked whether to merge to `main` with four phases outstanding, they chose
**"push only, stop here."** `main` is untouched at `72bd17f`; all five overhaul
commits live on the branch. **Do not merge without asking again.**

## The question still open, carried since Chunk 6

**No live LLM call has been made in any chunk of this overhaul.** Phase 3 made
none either — the only endpoint the UI calls is `/api/health`. The supervisor's
tool-calling loop, `Synthesizer.brief` against a real provider, and the trace for
a *freshly generated* brief remain unexercised against anything real.

It costs real tokens against the key in `.env`. **Ask before spending them.**
Phase 5 is where it stops being avoidable.

---

## What Phase 3 built, in one paragraph

`web/` — Vite 7, React 19, TypeScript, Tailwind v4, `lucide-react`. Four source
areas: `src/api/` (the hand-written typed client, 14 operations), `src/hooks/`
(`useTheme`, `useRequest`), `src/components/`, and `src/status.ts`. The only
screen is a status view rendering `/api/health`. Read the commit for the why.

## What Phase 4 must delete

Two blocks are explicitly build-state notes, not product, and they go when the
meeting list lands:

- The dashed placeholder in the `<nav>` of
  [web/src/components/Sidebar.tsx](../web/src/components/Sidebar.tsx).
- The "Not built yet" `<section>` at the bottom of
  [web/src/components/StatusPanel.tsx](../web/src/components/StatusPanel.tsx).

`StatusPanel` itself is worth keeping — it is what you read first when a brief
will not generate. It just stops being the only thing on screen.

## What Phase 4 can build on

- **Every operation it needs already exists** in
  [web/src/api/client.ts](../web/src/api/client.ts): `listMeetings`,
  `createMeeting`, `getMeeting`, `deleteMeeting`, `listMaterials`,
  `uploadMaterials`, `pasteMaterial`, `deleteMaterial`. None have been called
  from the UI yet — only `getHealth` has.
- **`useRequest(fetcher, deps)`** takes a dependency array, so a per-meeting fetch
  refires on selection, and it returns `reload` for after a mutation. It aborts in
  cleanup, which is what stops StrictMode's double-invoked effect from racing.
- **`ApiError.kind`** is populated for every `CopilotError`. `UnsupportedFileTypeError`
  (415) and `EmptyDocumentError` (422) are the two Phase 4 will actually see, and
  they deserve different copy from a generic failure.
- The palette tokens are in [web/src/index.css](../web/src/index.css). Semantic
  colours (`ok`/`warn`/`crit`) are deliberately separate from the accent — a
  successful upload and a selected meeting must not read as the same signal.

---

## Landmines specific to Phase 4

- **`web/dist/` is built and sitting on disk right now.** That means
  `api/main.py`'s `mount_frontend()` returns `True` at import and the SPA fallback
  is registered, replacing the handler for *every* `StarletteHTTPException`. This
  was verified not to break anything — 437 tests still pass and `/api/nope` is
  still a JSON 404 — but if you see route behaviour you did not expect, that is
  where to look. `rm -rf web/dist` restores the API-only behaviour.

- **The root `.gitignore` has unanchored `lib/`, `dist/`, `build/` entries** from
  its Python section. `dist/` usefully covers `web/dist/`, but `lib/` means **a
  `web/src/lib/` directory would be silently untracked** — a whole folder of source
  that never gets committed and that `git status` does not mention. Phase 3 used
  `src/api/` partly to sidestep this. If you want a `lib/`, fix the ignore file
  first with a leading slash.

- **The per-meeting lock is held across a whole brief run** — tens of seconds.
  Nothing on the server stops a client firing concurrent requests at the same
  meeting; they just queue invisibly. **Phase 4 must disable a meeting's upload and
  delete controls while its brief is generating.** This has been carried in every
  handoff since Phase 1 and is still not done, because nothing has generated a
  brief yet.

- **A multi-file upload is not all-or-nothing.** `POST .../materials` returns 200
  with `ingested` and `failed` both potentially non-zero and a per-file `error` in
  `results`. Rendering only the status code loses the failures entirely.

- **Do not set `Content-Type` on the upload request.** Only the browser knows the
  multipart boundary. `uploadMaterials` already omits it deliberately; setting it
  by hand produces a body FastAPI cannot parse and a 422 that blames the files.

- **`MeetingOut.title` is not trimmed.** The records layer stores what was written,
  trailing spaces included. Trim at display, not on the way in.

- **A real `.env` with live API keys sits in the repo root.** Gitignored. Never
  echo it. `tests/conftest.py` neutralises it and `tests/test_conftest_isolation.py`
  guards that — do not weaken it, or the suite reads live credentials and passes
  for the wrong reason.

---

## Environment facts

Node **v24.15.0**, npm **11.12.1**. Resolved frontend versions (in
`web/package-lock.json`):

```
react 19.2.8   vite 7.3.6   tailwindcss 4.3.3   typescript 5.9.3
lucide-react 0.545.0   @vitejs/plugin-react 5.2.0   @types/node 26.1.2
```

`@types/node` is required — `tsconfig.node.json` declares `"types": ["node"]` for
`vite.config.ts`, and without it `tsc -b` fails with TS2688 before anything else
is checked.

Python side, still **not in `requirements.txt`** (rewritten in Phase 7):

```
fastapi 0.140.13   uvicorn 0.51.0   python-multipart 0.0.32
```

Run both halves:

```bash
.venv/Scripts/python.exe -m uvicorn api.main:app --port 8077 --reload
```

```bash
npm run dev --prefix web
```

`.claude/launch.json` has a `web` configuration for the Vite server, so
`preview_start` with `{name: "web"}` works. Its `copilot` entry still launches the
Streamlit `app.py` and goes in Phase 7.

Vite is pinned to **5173** with `strictPort`, because `DEV_ORIGINS` in
`api/main.py` names that port and nothing else. It proxies `/api` to
`127.0.0.1:8077`, so **every client URL is relative and works unchanged in
production**, where FastAPI serves the bundle itself.

---

## Verification baseline

```bash
.venv/Scripts/python.exe -m pytest
```

```bash
.venv/Scripts/python.exe -m ruff check core/ tests/ agents/ scripts/ api/
```

```bash
npx tsc -b --prefix web
```

**437 tests pass** (~39s), ruff is clean, and the frontend typechecks — all three
verified with `web/dist/` present. `web/` has no test harness and the plan does
not ask for one. `app.py` is still outside the ruff scope and is deleted in Phase
7 rather than fixed.

### How Phase 3 was verified, and the thing that will bite you

**The Browser pane was not displayed in this session, so `computer` screenshots
timed out every time** ("the page is not compositing frames"). Two consequences:

- Verification was done with `read_page`, `get_page_text` and `javascript_tool`
  reading computed styles. That works well and is faster than screenshots for
  checking tokens, geometry and overflow. It cannot catch a purely visual defect.
- **`computer` clicks by `ref` resolved to bogus coordinates** (a button mid-page
  came back as y=0) and silently did nothing. Clicking via `javascript_tool`
  (`element.click()`) worked reliably. If a click appears to do nothing, this is
  why — do not go looking for a React bug first.

If the pane is available to you, take real screenshots; light and dark both need
looking at, and Phase 3 has never been seen by a human eye.

What was actually confirmed: all three `useRequest` states (skeleton, offline
callout with a working retry, live reading); the theme cycle through
system → light → dark persisting to `localStorage`; the drawer at 375px with no
horizontal overflow; no console errors; and the built bundle served same-origin
from FastAPI at `/`, including an unknown client-side route, while `/api/nope`
stays a JSON 404.

---

## Suggested skills for the next session

- **`run`** — Phases 4–6. Drive Vite through the Browser pane. Read the
  verification note above before concluding a click did not work.

- **`artifact-design`** — before writing new components, to stay calibrated. The
  user's brief is "looks like the ChatGPT website, clean and simple, no emojis but
  clean symbols". Phase 3 set the palette and type scale in
  [web/src/index.css](../web/src/index.css); extend it rather than introducing a
  second system.

- **`dataviz`** — Phase 5 only, if the trace timeline grows anything chart-shaped.
  Per-specialist hit/neighbour counts are the obvious candidate. Read it before
  choosing colours, not after.

- **`review`** — worth running at the Phase 6 boundary, before Phase 7's deletions
  make the diff large.

- **`tdd`** — only if you extend the API. The frontend has no test harness.

- **`handoff`** — at the next phase boundary. Note that this project keeps handoffs
  in `handoffs/` and commits them, rather than in the OS temp directory.

---

## Prompt for the next session

> Continue Chunk 8 of the LangGraph overhaul of `D:\hackathon\intelligence_copilot`,
> on branch `feat/react-frontend`. Read `handoffs/chunk8_part3_implemented.md`
> first, then `handoffs/chunk8_plan.md` for the phase plan.
>
> Phases 1–3 are done, committed at `6839e3c` and pushed. 437 tests pass, ruff
> clean, frontend typechecks. **Phase 4 is next: meetings and materials** — the
> meeting list and create form in the sidebar, selection driving the main column,
> drag-and-drop upload with per-file outcomes, paste-text, and a materials table
> with delete.
>
> The typed client already has every operation you need; only `getHealth` has been
> called from the UI so far. Delete the two build-state placeholder blocks the
> handoff names. Disable a meeting's upload controls while its brief is generating
> — the server holds a per-meeting lock for the whole run.
>
> Do not merge to `main`; the user decided to keep it untouched until the overhaul
> is finished. Ask before making any live LLM call — none has been made in this
> entire overhaul and it spends real tokens.
>
> Use `.venv/Scripts/python.exe`, not a bare `python`. Keep going phase by phase
> and commit at each boundary; do not attempt the rest of the chunk in one pass.
