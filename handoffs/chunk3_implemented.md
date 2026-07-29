# Handoff — Chunk 3 complete, resume at Chunk 4

**Date:** 2026-07-28
**Branch:** `overhaul/langgraph-multi-agent`
**Status:** Chunks 1–3 of 8 complete. Chunks 1–2 are committed (`e5317f1`, `f4691fb`);
Chunk 3 is **uncommitted** in the working tree.

Read `handoffs/chunk1_implemented.md` for the architecture decisions and environment
facts, and `chunk2_implemented.md` for the data layer. Neither is repeated here.

---

## What Chunk 3 delivered

| File | State |
|---|---|
| `core/chunk.py` | Rewritten — emits `NewChunk` with real offsets |
| `core/embed.py` | Rewritten — `Embedder` protocol + `VectorIndex` over `IndexIDMap2` |
| `core/indexing.py` | New — the write path (chunk → embed → store → index) |
| `core/recall.py` | Rewritten — `Retriever` returning `ScoredChunk`s |
| `core/document_handler.py` | **Deleted** |
| `scripts/reindex.py` | New — backfill / repair CLI |
| `tests/test_chunk.py`, `test_embed.py`, `test_indexing.py`, `test_recall.py` | New |
| `agents/copilot_orchestrator.py`, `app.py` | Minimal surgery to keep working |

**202 tests pass** (was 129), `~15s`, still no network and no model downloads in the
suite. Ruff is at 1 warning, in `core/llm_providers.py`, which Chunk 4 rewrites — plus
the legacy `.format()` noise in `agents/copilot_orchestrator.py`, which Chunk 6 replaces.
Leave both.

### The defect is now an assertion

`tests/test_indexing.py::test_re_chunking_never_returns_text_from_a_different_chunk`.
Store chunks, index them, delete a material, re-chunk the survivor with *different*
boundaries, search, and assert every returned id resolves to a live row whose text
slices back out of its own material at its own offsets. That is the bug, stated as a
test.

### `core/chunk.py`

`chunk_document(text, *, chunk_size=None, chunk_overlap=None, settings=None)
-> list[NewChunk]`. Defaults come from settings (900/150).

The invariant, pinned by tests: `material_text[c.char_start:c.char_end] == c.text` for
every chunk. Whitespace is trimmed off the **offsets**, then the text is sliced from the
trimmed span — the reverse order (slice, then `.strip()`, as the old code did) is what
made offsets impossible to add after the fact.

Boundary preference is `"\n\n"` → `". "` → `".\n"` → `"\n"` → hard cut, and a boundary is
only taken if it lands past 50% of the window. The loop breaks when a chunk reaches the
end of the document rather than stepping back by the overlap, because that step produced
a trailing chunk wholly contained in its predecessor, competing with its own source in
search results.

`chunk_text` / `chunk_text_large` are gone. Nothing imported them but the orchestrator.

### `core/embed.py`

- `Embedder` — a `Protocol` (`dim`, `encode`). This is why every function in the write
  and read paths takes an `embedder=` argument: `tests.fakes.HashingEmbedder` is lexical,
  so tests assert genuine relevance ordering with no model download.
- `SentenceTransformerEmbedder` — lazy model load, device from settings, and it **raises**
  if the model's dimension disagrees with `settings.embedding_dim` instead of writing an
  unreadable index.
- `get_model()` / `get_device()` / `encode()` are kept as module functions because
  `app.py`'s preloader calls them.
- `VectorIndex` — wraps `faiss.IndexIDMap2(IndexFlatIP(dim))`. `add(ids, vectors)`,
  `remove(ids)`, `search(vector, k) -> [(chunk_id, score)]`, `ids()`, `reset()`, `save()`.
  Ids are cast to `int64` at the boundary. FAISS's `-1` padding is filtered out inside
  `search`, so a sentinel can never escape as a row id.

`VectorIndex.open()` **discards** an existing file that is not id-mapped or has the wrong
dimension, and logs why. The pre-overhaul `.index` files store insertion positions; there
is no information in them that could be recovered into chunk ids, so adapting one would
mean guessing — which is the guess that caused the bug.

### `core/indexing.py`

The invariant this module owns: *every vector id in a meeting's index is the primary key
of a live `chunks` row holding exactly the text that was embedded.*

- `index_material(db, material_id)` — chunk, **embed, then** `replace_chunks`, then remove
  the superseded vectors and add the new ones. Embedding first is deliberate: it is the
  step that fails slowly, and failing there leaves the old rows and old vectors intact and
  consistent with each other.
- `delete_material_everywhere(db, material_id)` — captures the chunk ids, deletes, then
  drops those vectors. SQLite cascades cannot reach into a FAISS file; `app.py`'s delete
  button now calls this.
- `rebuild_meeting_index` — re-chunks everything, resets the index. New ids.
- `reindex_from_store` — re-embeds the **stored** chunks under their **existing** ids. Use
  this when the index is lost but the store is sound; re-chunking there would invalidate
  any `chunk_id` already cited in a stored brief.
- `check_index` → `IndexHealth(stored, indexed, missing, orphaned, healthy)`.
- `ensure_meeting_indexed` — the repair ladder: no chunks but materials → re-chunk;
  unhealthy → reindex from store; healthy → do nothing.

### `core/recall.py`

`Retriever(db, *, embedder=None, settings=None, auto_repair=True)`.

`recall(meeting_id, query="", k=None, *, neighbour_radius=None, min_similarity=None)
-> list[ScoredChunk]`:

1. `ensure_meeting_indexed` (unless `auto_repair=False`).
2. Search, over-fetching `k * 3`, then apply the similarity floor, then take `k` **hits**.
3. Hydrate with `get_chunks_by_ids(..., strict=True)` — an id with no row raises
   `IndexOutOfSyncError` rather than quietly shortening the result.
4. Expand each hit with `get_neighbour_chunks`, flagged `is_neighbour=True`. Neighbours
   are **additional** to `k`, ordered adjacent to their anchor in document order, so the
   model reads coherent runs. A chunk that is both a hit and a neighbour appears once, as
   the hit.

An **empty query** means "no particular question" (brief generation, not Q&A). It takes a
coverage sweep instead of a similarity search: meetings under `k * 3` chunks come back
whole; larger ones are sampled at even intervals through each material in proportion to
its length. This replaces the old ≤320k-character short-circuit that returned entire
documents and meant semantic search essentially never ran.

`format_context_blocks(results, *, labels=None)` emits a `Source: material_id#cN` line per
block and marks neighbours `(surrounding context)`. The orchestrator's
`_extract_sources_from_context` regex looks for exactly `Source: ` and had therefore
always found nothing; it works now.

---

## The real database was backfilled

`data/briefs.db` — backed up to `data/briefs.backup-20260728225842.db` (gitignored) before
the rebuild. After `python -m scripts.reindex --apply`:

- **5 meetings, 9 materials, 10 briefs** — unchanged.
- **872 chunks** across 5 meetings (822 of them in the one long AMI transcript).
- All 872 verified: `material.text[char_start:char_end] == chunk.text`, zero mismatches.
- All 5 indices `healthy` — no missing vectors, no orphans.
- `PRAGMA integrity_check` → `ok`; `PRAGMA foreign_key_check` → clean.
- The 6 old `data/faiss/*.index` files were deleted; indices are now
  `{meeting_id}.faiss`, matching `settings.index_path()`. `.gitignore` covers both.
- Retrieval smoke-tested against the real data with the real MiniLM model: hits score
  0.27–0.33, neighbours attach correctly, the sweep spans chunk indices 0→302.

---

## Start here: Chunk 4

LLM providers + prompts. `core/llm_providers.py` and `prompts/`.

1. **Load the `claude-api` skill before picking model IDs.** The current ones are stale
   (`claude-3-5-sonnet-20241022`, and `gpt-4` configured with an impossible
   `max_tokens=30000` — the OpenAI path could never have worked). Do not pick model IDs
   from memory.
2. `prompts/system_prompt.txt` is polluted: after the JSON rules it contains a full
   duplicate of the user prompt plus a chat-session changelog, all currently sent as the
   system message.
3. Replace the ~120 lines of markdown-fence stripping, regex comma repair and brace
   counting in `agents/copilot_orchestrator.py` with `BaseChatModel.with_structured_output`
   against `MeetingBrief`. That machinery exists because nothing ever asked the model for
   structured output.
4. `Evidence.chunk_id` is ready to populate — retrieval now returns real chunk ids, so a
   citation can be resolved back to its source span rather than trusted.
5. `core/synth.py` is still dead except `load_prompt_template` (imported by `app.py` and
   the orchestrator) and it imports `google.generativeai`, which is not in requirements.
   Chunk 7 deletes it.

---

## Commands

```bash
.venv/Scripts/python.exe -m pytest
```

```bash
.venv/Scripts/python.exe -m ruff check core/ tests/ scripts/
```

```bash
.venv/Scripts/python.exe -m scripts.reindex
```

---

## Landmines (in addition to Chunks 1–2's, which still apply)

- **`Retriever.recall` can write.** With `auto_repair=True` (the default) a read path may
  chunk and index a meeting before searching it. That is what keeps pre-overhaul meetings
  working, but it means the first recall after an upgrade is slow and takes a write lock.
  Pass `auto_repair=False` in tests that want to assert on a broken state.
- **Ids are never reused, so stale vectors are harmless but not free.** Deleting a
  material through `Database.delete_material` directly (rather than
  `delete_material_everywhere`) leaves its vectors in the index until the next repair.
  They resolve to nothing — detectable — but they still occupy the index and can crowd out
  real hits by taking result slots. Prefer `delete_material_everywhere`.
- **`chunk_size` is still capped by the embedder.** Do not raise it past ~1000 without
  changing the embedding model; `all-MiniLM-L6-v2` truncates at 256 word-pieces and the
  tail of a longer chunk is invisible to search.
- **The empty-query sweep is a placeholder for agent-chosen queries.** Chunk 5's agents
  should ask targeted questions ("open action items", "decisions", "risks") rather than
  relying on a queryless sweep, which samples evenly and can miss a section entirely.
- `tests/test_db_legacy_compat.py` is still temporary and still pins
  `Database.get_connection` — now used by `recall_context`'s raw-connection shim rather
  than the deleted `document_handler`. Delete both in Chunk 7.
- The suite went from ~7s to ~15s. Cost is FAISS index writes to `tmp_path`, not network.
