# Executive Intelligence Copilot

Turns a pile of meeting documents into an executive brief — a recap, open action
items, the topics worth raising, a timed agenda, and quoted evidence for each of
them — and answers follow-up questions against the same material.

Every claim in a brief is traceable. The UI shows what the system searched for,
which specialist found what, how much evidence survived the merge, and which
lines of enquiry failed, so a thin brief can be explained rather than guessed at.

---

## Architecture

Two LangGraph state graphs over a shared runtime. The shape is deliberate:
deterministic edges where the pipeline is fixed, an agent only where judgment is
actually needed.

```
                       brief graph
    START -> memory -> supervisor -=<  research (xN, parallel)  >=- merge
                                                                     |
                                                        +------------+------------+
                                                        |                         |
                                                   synthesize                   abort
                                                        |                         |
                                                     persist -------------------> END

                        Q&A graph
    START -> retrieve -=<  answer | no_context  >=- END
```

| Node | What it does |
|---|---|
| `memory` | Looks for a previous brief for the same meeting title and carries its action items forward |
| `supervisor` | An LLM agent with search tools decides what to look for. Optional — off, a standing roster of specialists runs instead, which is a complete plan on its own |
| `research` | One node per plan task, fanned out in parallel, each with its own query |
| `merge` | Merges the findings and caps the context; search hits survive the cut before the neighbouring chunks pulled in around them |
| `synthesize` | Writes the brief and validates it against the Pydantic schema |
| `abort` | The branch taken when there is nothing to write a brief from |
| `persist` | Stores the brief. **A brief that cannot be stored is still returned** — see below |

The two conditional edges are the only genuinely open decisions: *is there
anything here to write from* after the merge, and *is there anything to answer
from* after Q&A retrieval.

Graphs are compiled once per shape and cached. The runtime — database, retriever,
synthesizer, chat model — is passed at invocation time as context, so one
compiled graph serves every meeting.

### The success/error asymmetry

Worth knowing before reading any result dict or API response, because it is not
symmetric between the two graphs:

- **A brief** reports `ok` when *a document exists*. A brief that was generated
  and then failed to store comes back successful **with a warning**, because
  throwing away a usable document over a locked database serves nobody.
- **An answer** reports failure whenever an error is set. The graph answers "I
  could not find relevant information" without calling the model when nothing was
  retrieved — a legitimate success — but a retrieval *failure* lands on the same
  node, and reporting a real error as a polite non-answer would hide it.

### Technical stack

**Backend** — Python 3.11+, FastAPI, LangGraph 1.0 over LangChain 1.0, Pydantic
v2 throughout, SQLite via the stdlib `sqlite3`.

**Frontend** — React 19, TypeScript, Vite, Tailwind v4, `lucide-react`. The API
client is hand-written against `api/schemas.py` rather than generated.

**Retrieval** — `sentence-transformers` (`all-MiniLM-L6-v2`, 384-dim) for
embeddings, FAISS `IndexFlatIP` for search, one index per meeting.

**Providers** — Gemini (`gemini-2.5-flash`, the default), OpenAI (`gpt-4o`) or
Anthropic (`claude-opus-5`), selected with `LLM_PROVIDER`.

---

## Installation

```bash
git clone <repository-url>
cd intelligence_copilot
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
```

`requirements-dev.txt` includes `requirements.txt`, so that one command gets both
the app and the test tooling. For a deployment that will not run tests, install
`requirements.txt` alone.

Building the frontend additionally needs Node 20+ and npm.

Then copy `env.example` to `.env` and set `LLM_PROVIDER` and the matching API key.
`env.example` documents every setting `core/config.py` reads. Storage
directories are created on first run.

## Running it

**One port, production shape** — builds the React bundle, then serves it and the
API from the same FastAPI process. No CORS, no proxy, one URL:

```bash
python -m scripts.serve
```

That opens on <http://127.0.0.1:8000>. `--port`, `--host`, `--skip-build` and
`--build-only` are all available. The build has to finish *before* the app is
imported, because `api/main.py` decides whether it has a bundle to serve at
import time — which is the reason this wrapper exists rather than a bare uvicorn
command.

**Two ports, for frontend work** — Vite with hot reload, proxying `/api` to
uvicorn. Two terminals:

```bash
.venv/Scripts/python.exe -m uvicorn api.main:app --port 8077 --reload
```

```bash
npm run dev --prefix web
```

Then open <http://localhost:5173>. Vite is pinned to that port with
`strictPort`, because the API's CORS allowlist names it and nothing else — a
silent move to 5174 would fail every request with an opaque CORS error instead.

**API only** — uvicorn on its own serves the API perfectly well, and logs that it
found no bundle rather than treating it as an error.

Either way, **startup takes about twenty seconds**: the process builds the chat
client and loads the embedding model before accepting requests, so that the cost
lands before the first request rather than inside it. A health check that fails
in the first few seconds is not a fault.

---

## Usage

1. **Create a meeting** in the sidebar — title, date, attendees, tags.
2. **Add materials.** Drag in PDF, DOCX, PPTX or TXT files, or paste text. Each
   file is parsed, chunked, embedded and indexed in one operation, and reports its
   own outcome; one bad file in a batch does not sink the others.
3. **Generate a brief.** Recap, action items, topics, agenda and evidence, plus
   the plan that produced it, per-specialist findings with hit and neighbour
   counts, any failed enquiries, and a node-by-node timeline.
4. **Ask questions** against the indexed material. Answers carry grouped source
   citations and their own trace.

Briefs are versioned per meeting; the history dropdown loads any earlier one.
Export is JSON or Markdown.

**Cross-meeting memory:** a new meeting whose title matches an earlier one
inherits that meeting's context, so recurring meetings carry their action items
forward.

---

## HTTP API

Fourteen endpoints, all under `/api`. The interactive schema is at `/docs`.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/health` | Provider, model, device, storage, whether the supervisor is on |
| `GET` | `/api/meetings` | List meetings |
| `POST` | `/api/meetings` | Create a meeting (`201`) |
| `GET` | `/api/meetings/{id}` | One meeting |
| `DELETE` | `/api/meetings/{id}` | Delete a meeting and everything under it (`204`) |
| `GET` | `/api/meetings/{id}/materials` | List materials |
| `POST` | `/api/meetings/{id}/materials` | Upload files (multipart, multiple), per-file outcomes |
| `POST` | `/api/meetings/{id}/materials/text` | Add pasted text |
| `DELETE` | `/api/materials/{id}` | Delete a material and its vectors (`204`) |
| `POST` | `/api/meetings/{id}/brief` | Generate a brief — **costs tokens** |
| `GET` | `/api/meetings/{id}/briefs` | Brief history (stubs) |
| `GET` | `/api/meetings/{id}/brief/latest` | Most recent stored brief |
| `GET` | `/api/briefs/{id}` | One stored brief, validated against today's schema |
| `POST` | `/api/meetings/{id}/qa` | Ask a question — **costs tokens** |

Only the two marked endpoints call a provider. Everything else reads stored rows.

`core/exceptions.py`'s hierarchy is mapped to status codes by
`api/errors.py`, so a missing meeting is a `404` with a JSON body rather than a
`500`.

### Concurrency

`index_material`, `delete_material_everywhere` **and retrieval** all write a
meeting's FAISS index — retrieval does because it backfills anything unindexed.
Two of those at once on the same meeting corrupts the index file.

`api/deps.py` holds a **per-meeting** lock, not a global one, so a forty-second
brief on one meeting never blocks an upload to another.

---

## Project structure

```
intelligence_copilot/
├── api/                    FastAPI layer
│   ├── main.py             the ASGI app; mounts web/dist when it exists
│   ├── routes/             one module per resource
│   ├── schemas.py          request/response models
│   ├── translate.py        BriefRun/QaRun -> wire format
│   ├── errors.py           CopilotError -> HTTP status
│   └── deps.py             the process-wide runtime, and the per-meeting lock
│
├── agents/                 the LangGraph core
│   ├── graph.py            both graphs; run_brief_graph / run_qa_graph
│   ├── nodes.py            every node and routing function
│   ├── state.py            graph state models
│   ├── planner.py          the supervisor, and the standing roster it falls back to
│   ├── tools.py            the search tools the supervisor calls
│   ├── runtime.py          CopilotRuntime: the shared collaborators
│   └── copilot_orchestrator.py   pre-overhaul facade; what api/ calls
│
├── core/
│   ├── config.py           typed settings
│   ├── db.py               SQLite repository
│   ├── migrations.py       versioned schema
│   ├── parsing.py          PDF/DOCX/PPTX/TXT extraction
│   ├── chunk.py            chunking
│   ├── embed.py            embeddings and FAISS
│   ├── indexing.py         the write path, and index health checks
│   ├── recall.py           retrieval with neighbour expansion
│   ├── synthesis.py        prompt assembly and response parsing
│   ├── llm_providers.py    provider factory
│   ├── schema.py           MeetingBrief and friends
│   └── exceptions.py       the error hierarchy
│
├── web/                    React frontend (see web/src/)
├── prompts/                prompt templates
├── scripts/
│   ├── serve.py            build the frontend, serve both on one port
│   └── reindex.py          rebuild chunk stores and indices
├── tests/                  pytest; no network, no model downloads
├── data/                   SQLite file, FAISS indices, uploaded originals
├── requirements.txt        runtime pins
└── requirements-dev.txt    test and lint tooling; includes the above
```

---

## Database schema

Versioned migrations in `core/migrations.py`, tracked in a `schema_version`
table. `PRAGMA foreign_keys` is on for every connection.

**meetings** — `id`, `title`, `date`, `attendees`, `tags`, `created_at`

**materials** — `id`, `meeting_id`, `filename`, `media_type`, `text`,
`created_at`

**briefs** — `id`, `meeting_id`, `created_at`, `model`, `brief_json`

**chunks** — `id` (`INTEGER PRIMARY KEY AUTOINCREMENT`), `material_id`,
`meeting_id`, `chunk_index`, `text`, `char_start`, `char_end`, `created_at`

`AUTOINCREMENT` on `chunks.id` is load-bearing, not decorative: that id *is* the
FAISS vector id. Without it SQLite reuses `max(id) + 1` after a delete, and a
stale vector would then resolve to unrelated text — the retrieval-misalignment
defect this table exists to eliminate.

---

## Development

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

No test touches the network or downloads a model: `tests/fakes.py` provides a
hashing embedder and a scripted chat model, and the API tests drive a
`TestClient` against a `tmp_path` database.

Two warnings during the suite come from dependencies, not from this repo — one
from `fastapi.testclient` about httpx, one from inside LangGraph about
`AgentStatePydantic`, which nothing here imports.

### Logging

Standard-library logging, configured once by `core/logging_config.py`. Plain
format is `%H:%M:%S LEVEL logger.name | message`; set `LOG_FORMAT=json` for JSON
lines. Logger names are module paths (`core.indexing`, `agents.nodes`), so
`LOG_LEVEL` and per-logger filtering both work normally. Chatty third-party
loggers are pinned to `WARNING`.

### Storage

If the configured data directory is not writable, `Settings.prepare_storage`
relocates to a temporary one and the UI's status line says so, rather than
letting briefs quietly not survive a restart.

`scripts/reindex.py` rebuilds every chunk store and index from material text,
which is the source of truth. It reports by default and only writes with
`--apply`.

---

## Limitations

- Single-user: SQLite, and FAISS indices on the local filesystem.
- Text-based documents only — no audio or video transcription.
- No real-time collaboration.
- The supervisor's plan costs an extra LLM round trip with tool calls. Turn it
  off with `PLAN_WITH_LLM=false` to run the standing roster instead.

---

## License

See LICENSE.
