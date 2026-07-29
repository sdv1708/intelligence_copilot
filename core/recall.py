"""The read path: a question in, scored chunks of real source text out.

The previous implementation is worth describing, because everything here is a
reaction to it. It re-chunked every material at query time with a different
boundary rule than ingestion had used, searched a FAISS index whose vectors
were numbered by insertion position, and then looked up the hit by using that
position as an index into the freshly built Python list. The two orderings had
no reason to agree and generally did not, so a search returned text from a
different part of the document than the one that actually matched. Nothing
raised; the brief was simply about the wrong paragraph.

On top of that, `recall_with_context` returned entire documents without
searching at all whenever a meeting's materials totalled under 320k characters,
which was nearly always. Semantic search was, in practice, dead code.

Now: chunks are rows, vector ids are their primary keys, and a hit is resolved
by fetching that row. If the id is not there, `get_chunks_by_ids(strict=True)`
raises rather than returning something plausible.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from core.config import Settings, get_settings
from core.db import Database
from core.embed import Embedder, get_embedder
from core.indexing import ensure_meeting_indexed, open_index
from core.logging_config import get_logger
from core.schema import Chunk, ScoredChunk

logger = get_logger(__name__)

# Vector search is over-fetched before filtering, so that chunks discarded by
# the similarity floor do not eat into the requested number of hits.
_OVERFETCH = 3


class Retriever:
    """Semantic search over one database's chunk store."""

    def __init__(
        self,
        db: Database,
        *,
        embedder: Embedder | None = None,
        settings: Settings | None = None,
        auto_repair: bool = True,
    ) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.embedder = embedder or get_embedder(self.settings)
        # Meetings ingested before the chunk store existed have materials but
        # no chunks. Repairing on demand means those keep working instead of
        # returning nothing at all; set False to assert on a prepared state.
        self.auto_repair = auto_repair

    # --- Public API ---------------------------------------------------------

    def recall(
        self,
        meeting_id: str,
        query: str = "",
        k: int | None = None,
        *,
        neighbour_radius: int | None = None,
        min_similarity: float | None = None,
    ) -> list[ScoredChunk]:
        """Return the chunks most relevant to `query`, plus their neighbours.

        `k` bounds the number of *hits*. Neighbour chunks are additional: they
        are pulled in to restore the context that small, embedding-sized chunks
        cut through, and they are flagged `is_neighbour` so the prompt does not
        present filler as a strong match.

        An empty `query` means "no particular question" — brief generation, as
        opposed to Q&A. That takes a coverage sweep across the meeting rather
        than a similarity search, because scoring every chunk against a blank
        string ranks nothing.
        """
        k = k if k is not None else self.settings.retrieval_k
        radius = (
            neighbour_radius
            if neighbour_radius is not None
            else self.settings.neighbour_radius
        )
        floor = (
            min_similarity if min_similarity is not None else self.settings.min_similarity
        )

        if self.auto_repair:
            ensure_meeting_indexed(
                self.db, meeting_id, embedder=self.embedder, settings=self.settings
            )

        hits = (
            self._search(meeting_id, query, k, floor)
            if query.strip()
            else self._sweep(meeting_id, k)
        )
        if not hits:
            logger.info("No chunks recalled for meeting %s", meeting_id)
            return []

        return self._expand(hits, radius)

    def format_context(self, results: Sequence[ScoredChunk], meeting_id: str) -> str:
        """Format results for a prompt, labelling materials by filename."""
        labels = {
            material.id: material.filename or material.id
            for material in self.db.get_materials(meeting_id)
        }
        return format_context_blocks(results, labels=labels)

    # --- Internals ----------------------------------------------------------

    def _search(
        self, meeting_id: str, query: str, k: int, floor: float
    ) -> list[ScoredChunk]:
        index = open_index(meeting_id, self.settings)
        if index.ntotal == 0:
            logger.warning("Meeting %s has an empty vector index", meeting_id)
            return []

        query_vector = self.embedder.encode([query])
        scored = index.search(query_vector, k * _OVERFETCH)

        above_floor = [(cid, score) for cid, score in scored if score >= floor]
        if scored and not above_floor:
            logger.info(
                "Meeting %s: best similarity %.3f is below the floor of %.2f",
                meeting_id,
                scored[0][1],
                floor,
            )
        top = above_floor[:k]

        # strict=True on purpose: an id in the index with no row behind it is a
        # broken invariant, and quietly dropping it would hide exactly the
        # class of bug this rewrite exists to eliminate.
        chunks = self.db.get_chunks_by_ids([cid for cid, _ in top], strict=True)
        return [
            ScoredChunk(chunk=chunk, score=score)
            for chunk, (_, score) in zip(chunks, top, strict=True)
        ]

    def _sweep(self, meeting_id: str, k: int) -> list[ScoredChunk]:
        """Coverage sample across a meeting, for when there is no query.

        Small meetings come back whole. Larger ones are sampled at even
        intervals through each material, in proportion to its length, so the
        result spans the document instead of stopping after its first page --
        which is what returning the first `k` chunks would do.
        """
        chunks = self.db.get_chunks_for_meeting(meeting_id)
        if not chunks:
            return []

        # A sweep's hits get neighbours too, so the budget is what actually
        # fits rather than `k` exactly.
        if len(chunks) <= k * _OVERFETCH:
            return [ScoredChunk(chunk=chunk, score=1.0) for chunk in chunks]

        by_material: dict[str, list[Chunk]] = {}
        for chunk in chunks:
            by_material.setdefault(chunk.material_id, []).append(chunk)

        selected: list[Chunk] = []
        for material_chunks in by_material.values():
            share = max(1, round(k * len(material_chunks) / len(chunks)))
            step = len(material_chunks) / share
            selected.extend(
                material_chunks[min(int(i * step), len(material_chunks) - 1)]
                for i in range(share)
            )

        selected.sort(key=lambda c: (c.material_id, c.chunk_index))
        return [ScoredChunk(chunk=chunk, score=1.0) for chunk in selected]

    def _expand(self, hits: Sequence[ScoredChunk], radius: int) -> list[ScoredChunk]:
        """Interleave each hit with its neighbouring chunks.

        Order is by hit rank, and each hit is immediately followed by the
        chunks around it in document order, so the model reads coherent runs of
        source text rather than a shuffled list of fragments. A chunk that is
        both a hit and someone else's neighbour appears once, as the hit.
        """
        results: list[ScoredChunk] = []
        seen = {scored.chunk.id for scored in hits}

        for scored in hits:
            group = [scored]
            if radius > 0:
                for neighbour in self.db.get_neighbour_chunks(scored.chunk.id, radius):
                    if neighbour.id in seen:
                        continue
                    seen.add(neighbour.id)
                    group.append(
                        ScoredChunk(
                            chunk=neighbour, score=scored.score, is_neighbour=True
                        )
                    )
            group.sort(key=lambda s: s.chunk.chunk_index)
            results.extend(group)

        logger.info(
            "Recalled %d chunks (%d hits, %d neighbours)",
            len(results),
            len(hits),
            len(results) - len(hits),
        )
        return results


# --- Formatting -------------------------------------------------------------


def format_context_blocks(
    results: Sequence[ScoredChunk],
    *,
    labels: Mapping[str, str] | None = None,
) -> str:
    """Render retrieved chunks as the context section of a prompt.

    Each block carries a `Source:` line naming `material_id#cN`, which is the
    citation the model is asked to quote back in `Evidence.source` and which
    maps to a single chunk row.
    """
    if not results:
        return "No context retrieved."

    labels = labels or {}
    blocks: list[str] = []
    current_material: str | None = None

    for position, scored in enumerate(results, start=1):
        chunk = scored.chunk
        if chunk.material_id != current_material:
            if current_material is not None:
                blocks.append("")
            current_material = chunk.material_id
            title = labels.get(chunk.material_id)
            heading = (
                f"{title} ({chunk.material_id})" if title else chunk.material_id
            )
            blocks.append(f"=== Material: {heading} ===")

        kind = " (surrounding context)" if scored.is_neighbour else ""
        blocks.append(
            f"[{position}] Source: {chunk.source_ref}{kind}\n"
            f"Score: {scored.score:.3f}\n"
            f"{chunk.text}\n---"
        )

    return "\n".join(blocks)
