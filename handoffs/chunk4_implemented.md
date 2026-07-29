# Handoff — Chunk 4 complete, resume at Chunk 5

**Date:** 2026-07-28
**Branch:** `main` (chunks 1–3 are committed here: `e5317f1`, `f4691fb`, `96509ca`)
**Status:** Chunks 1–4 of 8 complete. Chunk 4 is **uncommitted** in the working tree.

Read `handoffs/chunk1_implemented.md` for the architecture decisions and environment
facts, `chunk2_implemented.md` for the data layer, and `chunk3_implemented.md` for
retrieval. None of that is repeated here.

---

## What Chunk 4 delivered

| File | State |
|---|---|
| `core/llm_providers.py` | Rewritten — provider factory, current model ids, per-provider quirks |
| `core/prompts.py` | New — template loading and **strict** rendering |
| `core/synthesis.py` | New — structured brief generation, grounded Q&A, citation resolution |
| `core/config.py` | Model ids, `llm_max_tokens`, `model_for()` |
| `core/exceptions.py` | `PromptError` |
| `prompts/*.txt` | All four rewritten |
| `agents/copilot_orchestrator.py` | ~150 lines of JSON repair deleted; wired to the above |
| `tests/fakes.py` | `ScriptedChatModel` now implements `with_structured_output` |
| `tests/test_prompts.py`, `test_llm_providers.py`, `test_synthesis.py` | New |
| `env.example` | Model-selection section |

**274 tests pass** (was 202), `~23s`, still no network and no model downloads in the
suite. `ruff check core/ tests/ scripts/` is clean. The remaining ~18 warnings are all
legacy `.format()` calls in `agents/copilot_orchestrator.py`, which Chunk 6 replaces —
leave them.

### Model ids are configuration now, and the old ones were dead

`claude-3-5-sonnet-20241022` was **retired in October 2025**: the Anthropic path returned
a 404 for anyone who selected it. `gpt-4` was configured with `max_tokens=30000` against
an 8192-token output cap, so the OpenAI path could never have completed a request either.
Only Gemini worked, which is why it was the default.

Defaults, all overridable (`ANTHROPIC_MODEL` / `OPENAI_MODEL` / `GEMINI_MODEL`):

| Provider | Model | Note |
|---|---|---|
| Anthropic | `claude-opus-5` | Current Opus; thinks by default, so `max_tokens` covers reasoning too |
| OpenAI | `gpt-4o` | Chosen for stability; a GPT-5 id also works, see below |
| Gemini | `gemini-2.5-flash` | Was `gemini-2.5-flash-lite` |

`tests/test_llm_providers.py::test_default_model_ids_are_not_retired` pins the retired
ids so a stale default cannot come back silently.

### `temperature` is not universal any more

Claude Opus 4.7+, Claude Sonnet 5, and the GPT-5 family **reject** `temperature` with a
400 — it is not ignored. `NO_SAMPLING_PARAMS` in `core/llm_providers.py` lists those
families and `build_chat_model` omits the parameter for them, matching on prefix so
dated snapshots are covered. Add a family to that tuple rather than special-casing a
call site.

### Structured output replaces the repair machinery

`core/synthesis.py` binds `MeetingBrief` through `BaseChatModel.with_structured_output`.
Deleted from the orchestrator: markdown-fence stripping (two variants), regex removal of
trailing commas and `//` and `/* */` comments, `_repair_incomplete_json` (brace and
bracket counting, string closing, line truncation), the debug-file dump, and
`_extract_sources_from_context`. All of it existed because nothing ever *asked* the model
for structured output.

Two deliberate choices:

- **`method="function_calling"`** wherever the provider offers a choice. OpenAI now
  defaults to strict `json_schema`, and strict mode rejects the `min_length` / `gt` / `le`
  constraints `MeetingBrief` uses. `structured()` detects the option by inspecting the
  signature, so Anthropic (which has no `method`) is left alone.
- **`include_raw=True`.** A failed parse arrives as data, not an exception, so the raw
  response can be logged as itself.

The only repair kept is supplying `meeting_title` from the caller when the model omits it
— a required field we already know the answer to. Everything else that fails validation
raises `InvalidBriefError`. `tests/test_synthesis.py::test_prose_wrapped_in_a_markdown_fence_is_a_failure_not_a_repair`
pins that the old behaviour does not creep back.

### Citations are resolved, not trusted

`resolve_evidence(evidence, results)` looks each `Evidence.source` up against the
`source_ref`s of the chunks that were actually retrieved:

- A match populates `Evidence.chunk_id` with the real row id, so a stored brief can be
  traced back to the exact span years later.
- A decorated citation (`"[2] mat_b#c4 (transcript)"`) is canonicalised.
- A citation matching nothing is **dropped**, and returned in `BriefSynthesis.dropped_sources`
  for logging. A citation pointing at text that was never retrieved is worse than none.

Neighbour chunks are quotable — they are real retrieved text, just not search hits.

Q&A sources now come from the retrieved chunks rather than a regex over the rendered
prompt. The old regex looked for `Source: ` in a string that never contained it, so
**every answer had been returned with an empty source list**.

### Prompts

`prompts/system_prompt.txt` had accumulated a verbatim copy of the user prompt, the JSON
schema, and a changelog from the chat session that produced it — all of it sent as the
system message. Rewritten, along with the other three:

- The JSON formatting rules are gone from every prompt. The schema is bound, not described.
- `user_prompt.txt` gained a `{{previous_meeting}}` placeholder; cross-meeting memory is
  rendered by `core.synthesis.format_previous_brief` instead of being string-concatenated
  onto the front of the prompt by the orchestrator.
- The Q&A prompts kept their directness but no longer instruct the model to be
  "definitive" and to answer from general knowledge when the documents are thin — that
  pairing is a hallucination generator in a grounded-QA product. They now require the
  seam between "what the materials say" and "what I advise" to be visible.

`core/prompts.py` renders **strictly**: every declared placeholder must be supplied, every
supplied value must correspond to a placeholder, and a value that itself contains
`{{...}}` is rejected. Templates resolve against the package, so the app no longer breaks
when launched from outside the repo root, and a missing file raises instead of returning
`""` (which used to mean the model was asked for a brief with no instructions at all).

---

## Verified end to end, offline

Ingest → chunk → index → recall → structured brief → citation resolution → persistence →
Q&A, with the real MiniLM embedder and a scripted chat model, against a throwaway
database. The fabricated citation was dropped, the real one persisted with
`chunk_id: 1`, and Q&A came back with four sources.

**No live API call has been made.** The structured-output path has not been exercised
against a real provider — that is the highest-value next verification and it needs the
user's key and their sign-off, since it sends content to a third party.

---

## Start here: Chunk 5

The LangGraph multi-agent core. This is the chunk the whole overhaul is named after.

1. **Supervisor + specialist nodes**, per the decision in Chunk 1: deterministic edges
   where the pipeline is fixed, tool-calling agents where judgment is needed. APIs
   confirmed present in the venv: `langgraph.graph.StateGraph`,
   `langgraph.checkpoint.memory.InMemorySaver`, `langchain.agents.create_agent`,
   `langchain_core.tools.tool`.
2. **`core/synthesis.py` is the node body you want.** `Synthesizer` takes a chat model
   rather than building one, so a graph can share one client across nodes, and both
   `brief()` and `answer()` are pure functions of (prompt inputs, retrieved chunks).
3. **Give the agents real queries.** Chunk 3's empty-query coverage sweep is a
   placeholder. Specialist nodes should ask targeted questions — "open action items",
   "decisions taken", "risks and blockers", "dates and deadlines" — and merge the
   results. `Retriever.recall(meeting_id, query=...)` already does the work; nothing
   calls it with a real query yet outside Q&A.
4. **Citation resolution belongs after the merge.** `resolve_evidence` takes whatever
   chunk set you hand it, so run it against the union of every node's retrieval, or a
   node's citations to another node's chunks will be dropped as fabricated.
5. `format_previous_brief` is the memory-node output format. `_get_previous_meeting_brief`
   in the orchestrator is the query; move it into a node and delete the method.

---

## Commands

```bash
.venv/Scripts/python.exe -m pytest
```

```bash
.venv/Scripts/python.exe -m ruff check core/ tests/ scripts/
```

---

## Landmines (in addition to Chunks 1–3's, which still apply)

- **`claude-opus-5` thinks by default and `max_tokens` covers the thinking.** The 16000
  default has room; if you lower `LLM_MAX_TOKENS` for cost, a brief can truncate
  mid-generation on that model. On Opus 5, disabling thinking is only legal at effort
  `high` or below — do not add a `thinking={"type": "disabled"}` without reading the
  `claude-api` skill first.
- **Do not pick model ids from memory.** Load the `claude-api` skill before touching
  Anthropic ids; check the provider's own docs for OpenAI and Gemini. The OpenAI default
  is `gpt-4o` rather than a GPT-5 id specifically because GPT-5 also rejects
  `temperature` and the trade-off deserves a deliberate decision, not a silent default.
  If you switch it, `NO_SAMPLING_PARAMS` already covers the `gpt-5` prefix.
- **Prompt templates are cached for the process.** Editing a `.txt` while Streamlit is
  running has no effect until restart, or a call to `clear_prompt_cache()`.
- **`Evidence.chunk_id` is only meaningful for briefs written from now on.** The ten
  stored briefs predate it and have `None` throughout. Anything that resolves a citation
  to source text must handle that.
- **`Synthesizer.brief` refuses to run with no context** (`SynthesisError`) rather than
  generating an ungrounded brief. The orchestrator turns that into
  `{"success": False, "error": ...}`; a Chunk 5 node should decide deliberately whether
  to fail the graph or degrade.
- `core/synth.py` is still dead except `load_prompt_template`, which `app.py` still
  imports. `core/prompts.py` supersedes it — point `app.py` at the new one and delete the
  module in Chunk 7.
