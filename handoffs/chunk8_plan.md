# Chunk 8 plan — replace Streamlit with a FastAPI + React UI

**Date:** 2026-07-29
**Supersedes:** the "rewrite `app.py`" description in `handoffs/chunk7_implemented.md`.

## Decisions already made

| Question | Answer |
|---|---|
| Frontend | React + TypeScript + Vite + Tailwind v4 |
| Look | ChatGPT-like: neutral palette, centred content column, no emoji, `lucide-react` icons |
| Live trace over SSE | **No.** Plain request/response. The trace renders as a timeline after the fact. |
| Existing `app.py` | **Delete** in the final phase, once the React UI covers everything it did. |
| Backend | FastAPI over the existing `CopilotOrchestrator` facade — no orchestration logic moves |

## Why this is cheaper than it looks

- Every model is Pydantic v2 already, so response models are nearly free.
- `Database` opens a connection per call and documents that connections must not
  cross threads ([core/db.py:62](core/db.py:62)) — FastAPI's threadpool works as-is.
- `st.cache_resource` singletons become one startup-built `CopilotRuntime`.

## The one real concurrency hazard

`index_material`, `delete_material_everywhere` **and `Retriever.recall`** all write
`settings.index_path(meeting_id)` — recall does because `ensure_meeting_indexed`
backfills. Two at once on the same meeting corrupts the index file.

Mitigation: a **per-meeting** lock in `api/deps.py`, not a global one. Same meeting
serializes; a 40-second brief on meeting A never blocks an upload to meeting B.

---

## Phases

Each phase ends with the app in a working state and a commit. No phase depends on
a later one being finished.

### Phase 1 — Backend: routes and app

**Status: partly written, uncommitted.** `api/__init__.py`, `api/schemas.py`,
`api/deps.py`, `api/translate.py` exist. Remaining: `api/routes/` and `api/main.py`.

Endpoints:

| Method | Path | Facade call |
|---|---|---|
| GET | `/api/health` | settings + device + provider |
| GET/POST | `/api/meetings` | `list_meetings` / `create_meeting` |
| GET/DELETE | `/api/meetings/{id}` | `get_meeting` / `delete_meeting` |
| GET | `/api/meetings/{id}/materials` | `get_materials` |
| POST | `/api/meetings/{id}/materials` | `ingest_material` (multipart, multi-file) |
| POST | `/api/meetings/{id}/materials/text` | `ingest_material` (pasted) |
| DELETE | `/api/materials/{id}` | `delete_material_everywhere` |
| POST | `/api/meetings/{id}/brief` | `generate_brief` |
| GET | `/api/meetings/{id}/briefs` | `get_brief_history` |
| GET | `/api/briefs/{id}` | `get_brief_by_id` → `as_brief()` |
| POST | `/api/meetings/{id}/qa` | `answer_question` |

Plus a `CopilotError` → HTTP exception handler so the hierarchy in
`core/exceptions.py` maps to sensible status codes instead of 500s.

**Verify:** uvicorn boots; every endpoint exercised with `curl` against the real
`data/briefs.db` (5 meetings, 5 briefs). No live LLM call yet — brief/QA endpoints
verified for wiring, not output.

### Phase 2 — API tests

`tests/test_api.py` using `TestClient` and the existing `tests/fakes.py`
(`HashingEmbedder`, `ScriptedChatModel`) against a `tmp_path` database, so the suite
still makes no network calls and downloads no models. Covers the status-code mapping,
the multi-file partial-failure path, and the `ok`/`warning` asymmetry in
`api/translate.py`.

**Verify:** full suite green (368 existing + new), ruff clean over `api/`.

### Phase 3 — Frontend shell

`web/` — Vite, React 19, TS, Tailwind v4, `lucide-react`. Typed API client generated
by hand from `api/schemas.py` (not codegen — one file, and hand-writing it is the
review). Layout only: sidebar, centred content column, light/dark, health status line.

**Verify:** `npm run dev` in the Browser pane, screenshot, no console errors.

### Phase 4 — Meetings and materials

Meeting list, create form, selection. Drag-and-drop upload with per-file outcomes,
paste-text, materials table with delete.

**Verify:** create a meeting, upload a real PDF from `sample_data/`, delete it.

### Phase 5 — Brief and trace

The brief itself (recap, action items, topics, agenda, evidence) plus the piece
Streamlit could not show: plan, per-specialist findings with hit/neighbour counts,
failed enquiries, node timeline. History dropdown, JSON/Markdown export.

**Verify:** load a stored brief from the real database end to end.

### Phase 6 — Q&A

Composer-style input, conversation thread, source citations, per-answer trace.

**Verify:** ask a question against an indexed meeting.

### Phase 7 — Cleanup

Delete `app.py`. Rewrite `requirements.txt` (currently pins `langchain==0.3.7`
against a venv holding `1.0.5`). Fix `README.md` — it still documents `[INFO]`/`[OK]`
log prefixes and `[IngestionTool]`/`[RecallTool]` class names that no longer exist.
Add a run script that serves the built frontend from FastAPI on one port.
Write `handoffs/chunk8_implemented.md`.

---

## Open item, carried from Chunk 6

**No live API call has been made in any chunk.** The supervisor's tool-calling loop,
`Synthesizer.brief` against a real provider, and the trace for a *freshly generated*
brief remain exercised only against fakes. Phases 5 and 6 are the natural moment to
finally do it — but it costs real tokens against the key in `.env`, so it needs
explicit sign-off.
