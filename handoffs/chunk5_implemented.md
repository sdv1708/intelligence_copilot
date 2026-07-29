# Handoff — Chunk 5 complete, resume at Chunk 6

**Date:** 2026-07-29
**Branch:** `main` (chunks 1–4 are committed here: `e5317f1`, `f4691fb`, `96509ca`, `691f3ec`)
**Status:** Chunks 1–5 of 8 complete. Chunk 5 is **uncommitted** in the working tree.

Read `handoffs/chunk1_implemented.md` for the architecture decisions and environment
facts, `chunk2` for the data layer, `chunk3` for retrieval, and `chunk4` for providers,
prompts and synthesis. None of that is repeated here.

---

## What Chunk 5 delivered

The LangGraph multi-agent core — the chunk the overhaul is named after.

| File | State |
|---|---|
| `agents/state.py` | New — `ResearchTask`, `ResearchPlan`, `Finding`, `BriefState`, `QaState` |
| `agents/runtime.py` | New — `CopilotRuntime`, the context object every node reads from |
| `agents/tools.py` | New — `list_materials` / `search_meeting`, scoped to one meeting |
| `agents/planner.py` | New — the supervisor agent, and the roster it falls back to |
| `agents/nodes.py` | New — every node body, plus `merge_findings` |
| `agents/graph.py` | New — the two graphs, `run_brief_graph` / `run_qa_graph` |
| `agents/__init__.py` | Lazy re-exports; `import agents` stays cheap |
| `agents/copilot_orchestrator.py` | `_get_previous_meeting_brief` deleted, now a node |
| `prompts/planner_system.txt`, `planner_user.txt` | New |
| `core/config.py` | `research_k`, `brief_max_chunks`, `plan_with_llm`, `planner_max_tasks` |
| `core/prompts.py` | `PLANNER_SYSTEM`, `PLANNER_USER` |
| `tests/fakes.py` | `ScriptedToolCallingModel` — a real `BaseChatModel` |
| `tests/agentworld.py` | New — the ingested meeting the agent tests run against |
| `tests/test_planner.py`, `test_nodes.py`, `test_graph.py` | New |

**340 tests pass** (was 274), `~30s`, still no network and no model downloads in the
suite. Ruff is at 16 warnings, all `.format()` calls in
`agents/copilot_orchestrator.py`, which Chunk 6 replaces — leave them.

---

## The shape

```
                       brief graph
    START -> memory -> supervisor -=<  research (xN, parallel)  >=- merge
                                                                     |
                                                        +------------+------------+
                                                        |                         |
                                                   synthesize                   abort
                                                        |                         |
                                                     persist -------------------> END
```

```
                        Q&A graph
    START -> retrieve -=<  answer | no_context  >=- END
```

Deterministic edges where the pipeline is fixed, an agent where judgment is needed —
the decision from Chunk 1, made concrete. The three places the path is genuinely open
are the supervisor node and the two conditional edges; everything else happens in the
same order every time and is wired as a plain edge.

`CopilotRuntime` carries `db`, `settings`, `retriever`, `synthesizer` and the planner
model, and is passed as LangGraph **context** (`graph.invoke(state, context=runtime)`).
No node builds a collaborator of its own. That is what lets the whole pipeline run
against a `tmp_path` SQLite file, `HashingEmbedder` and a scripted model.

Graphs are compiled once per shape and cached (`brief_graph()`, `qa_graph()`), because
the runtime arrives at invocation time. One compiled graph serves every meeting.

---

## The supervisor is real, and it is never load-bearing

`agents/planner.py` builds a `langchain.agents.create_agent` with the two corpus tools
and `response_format=ResearchPlan`. It probes the materials, then commissions the
questions. It is **on by default** (`PLAN_WITH_LLM=true`) — one extra round trip buys
questions aimed at this meeting rather than a generic five.

Every failure path returns `DEFAULT_ROSTER` instead: a provider error, a timeout, a
malformed plan, an empty plan, or the supervisor being switched off. The reason lands in
`plan_rationale` and in the trace, so a fallback reads as a fallback rather than as a
deliberate choice. This is not defensiveness for its own sake — the pre-overhaul system
had no planning step and still produced briefs, so a planner that can fail the run would
be a regression wearing an upgrade's clothes.

`DEFAULT_ROSTER` is five tasks: a **coverage sweep** (empty query, which
`Retriever.recall` treats as "no particular question") plus `action_items`, `decisions`,
`risks` and `timeline`. Those four map onto the sections `prompts/user_prompt.txt` asks
the writer to fill in; plan and prompt are meant to be read together, and changing one
without the other is how a section quietly loses its evidence.

`_usable_tasks` drops duplicate queries, drops a second sweep, disambiguates repeated
names, and truncates at `planner_max_tasks`. A plan is capped, never rejected.

### Chunk 3's placeholder is gone

`tests/test_graph.py::test_every_planned_query_is_actually_issued` asserts each roster
query reaches the embedder. Before this chunk, `Retriever.recall(meeting_id, query=...)`
was called with a real query only from Q&A; brief generation always took the queryless
sweep, which samples evenly and can miss a section entirely.

---

## Merging is where citations are saved

`merge_findings` unions every specialist's results before synthesis, and this ordering
is load-bearing. `resolve_evidence` drops any citation it cannot find among the chunks
it was handed, so if the writer quotes a passage the risks specialist retrieved and
resolution runs against one branch's chunks, a perfectly good citation is discarded as
fabricated. Both halves are pinned:
`test_a_citation_only_one_specialist_found_survives_the_merge` and
`test_that_same_citation_is_dropped_when_nobody_retrieved_it`.

Three rules, in this order:

- A chunk two specialists both found appears **once**.
- A **hit beats a neighbour** for the same chunk, even when the neighbour scored higher.
  The prompt must not label a real match `(surrounding context)`.
- Output is in **document order**, not rank order — a brief is read whole, so coherent
  runs beat a ranked shuffle. Rank still decides what survives `brief_max_chunks`, and
  neighbours are discarded before hits.

---

## Degradation, decided rather than inherited

The Chunk 4 landmine asked for a deliberate choice about `SynthesisError` on empty
context. The choices made:

| Failure | Behaviour |
|---|---|
| One specialist's retrieval raises | That `Finding` carries the error; the other branches proceed. This is what the fan-out buys. |
| **Every** search returns nothing | `merge` sets `error` and routes to `abort`. **The model is never called.** |
| Model returns prose instead of a brief | `InvalidBriefError` → `run.error`, no brief, nothing stored. |
| Brief generated, storage fails | `run.ok` is **True** with `error` set. Throwing away a usable document because SQLite was locked serves nobody. |
| Q&A retrieves nothing | `no_context` node answers without calling the model. Asking a grounded-QA model to answer with no context is asking it to invent, and paying for it. |

`BriefRun.ok` therefore means *a brief exists*, not *nothing went wrong*. Read `error`
too.

Node bodies catch `CopilotError` and its subclasses only. A `TypeError` in `agents/`
propagates — swallowing it into `state["error"]` would turn a bug in this code into a
support ticket about the model.

---

## Observability

Every node appends to `state["notes"]`, merged by a reducer. A real run reads:

```
memory: no previous meeting on record
supervisor: standing roster -> overview, action_items, decisions, risks, timeline
overview: swept -> 6 hit(s), 10 neighbour(s)
action_items: searched 'open action items, outstanding tasks, who is respons...' -> 6 hit(s), 12 neighbour(s)
...
merge: 60 chunk(s) from 5 search(es) (27 hit(s), 33 neighbour(s))
synthesis: 1 action item(s), 1 topic(s), 3 citation(s) resolved, 1 citation(s) dropped as unmatched
persistence: stored as brief_20260729063605_6b58e5fb
```

This replaces the `log_message("[Step 2]")` calls and is what Chunk 8 should render as a
progress trace. `BriefRun` also exposes `plan`, `plan_source`, `findings`,
`failed_tasks`, and `results`.

---

## Verified end to end, offline

Against a **copy** of the real `data/briefs.db` (5 meetings, 872 chunks) with the real
MiniLM embedder and a scripted chat model. The real database was not written to.

On the 822-chunk AMI transcript: five specialists returned 30 hits, merged to 27 distinct
(three chunks were found by two specialists each), capped from 80 to 60 with all 27 hits
retained. Three real citations resolved to live chunk ids whose `source_ref` matched;
one fabricated citation was dropped. The brief persisted, and Q&A came back with 12
sources.

**No live API call has been made, in this chunk or any previous one.** The supervisor's
tool-calling loop and the structured-output path have both been exercised only against
fakes. Running them against a real provider is still the highest-value next verification
and still needs the user's key and their sign-off.

---

## Start here: Chunk 6

Compatibility facade + wire `app.py`.

1. **`CopilotOrchestrator` becomes a thin facade over the graphs.** Keep the four public
   signatures `app.py` calls (`ingest_material`, `recall_context_tool`, `generate_brief`,
   `answer_question`, `recall_previous_brief`) and have `generate_brief` /
   `answer_question` delegate to `run_brief_graph` / `run_qa_graph`. Build one
   `CopilotRuntime` in `__init__` via `CopilotRuntime.build(provider=...)`.
2. **Map `BriefRun` onto the old dict.** `{"success": run.ok, "brief": run.brief,
   "brief_id": ..., "provider": ..., "model": ...}` — and note `ok` is True with an
   `error` set when persistence failed, so `success` alone is not the whole story.
3. **Point `app.py` at `core/prompts.load_prompt_template`** instead of
   `core/synth.load_prompt_template`; that is the last import keeping `core/synth.py`
   alive, and Chunk 7 deletes the module.
4. Surface `run.notes` in the UI in place of the `log_message` trace — the data is
   already there and it is most of what Chunk 8 needs.
5. Run the `run` skill afterwards. The app should genuinely boot and generate a brief,
   not merely import.

---

## Commands

```bash
.venv/Scripts/python.exe -m pytest
```

```bash
.venv/Scripts/python.exe -m ruff check core/ tests/ agents/ scripts/
```

---

## Landmines (in addition to Chunks 1–4's, which still apply)

- **The supervisor doubles the LLM round trips per brief**, and its tool loop can add
  more. `PLAN_WITH_LLM=false` runs the roster and costs one call total. Decide this
  deliberately before pointing it at a paid provider.
- **`plan_research` catches bare `Exception`.** That is intentional — the roster is
  always a valid answer — but it means a genuine bug inside the planner surfaces as
  "supervisor failed (…)" in the trace rather than as a traceback. Check the log line
  before concluding the model misbehaved.
- **Roster queries are only as separable as the corpus.** On the AMI transcript,
  `overview` and `timeline` both top out on the same chunk: conversational speech does
  not partition into "decisions" and "risks" the way minutes do. The merge handles the
  overlap correctly, but do not read distinct task names as evidence of distinct
  evidence.
- **`brief_max_chunks` is a token budget with no token counting behind it.** 60 chunks
  of ~900 characters is roughly 13k tokens of context. Raising it on a long transcript
  can crowd out the instructions before it hits any provider limit.
- **`merge_findings` returns document order, so the highest-scoring chunk is not first.**
  Anything that assumes `results[0]` is the best match — a "top source" UI element, for
  instance — must sort by score itself.
- **A checkpointed graph needs a `thread_id`.** `run_*_graph(thread_id=...)` only sends
  one when asked; compile with `build_brief_graph(checkpointer=...)` and pass a thread
  id, or LangGraph raises. The cached `brief_graph()` / `qa_graph()` have no
  checkpointer and are therefore stateless and safe to share process-wide.
- **`tests/agentworld.py` pins chunk indices.** `ACTION_ITEMS_CHUNK = 1`,
  `RISKS_CHUNK = 2`, `TIMELINE_CHUNK = 3` in `test_graph.py` depend on the corpus text
  *and* on `chunk_size=280, chunk_overlap=0`. Editing `PARAGRAPHS` will silently move
  them; the citation tests will fail loudly, which is the intended alarm.
- `core/synth.py` is still dead except `load_prompt_template`, which `app.py` still
  imports. Chunk 6 repoints it, Chunk 7 deletes the module.
