"""The write path: material text in, chunk rows and vectors out.

This module owns the one invariant the whole retrieval design rests on:

    every vector id in a meeting's index is the primary key of a live row in
    the `chunks` table, and that row holds exactly the text that was embedded.

Everything here exists to establish or restore that. Chunking, id assignment
and embedding happen in one place, in a fixed order, so there is no path
through the system that writes a vector without also writing the row it names.

The order is deliberate: the text is embedded *before* the database rows are
replaced. Embedding is the step that can fail slowly (a model download, an OOM
on the GPU), and failing there leaves the previous chunks and the previous
vectors both intact and consistent with each other.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.chunk import chunk_document
from core.config import Settings, get_settings
from core.db import Database
from core.embed import Embedder, VectorIndex, get_embedder
from core.exceptions import StorageError
from core.logging_config import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class IndexReport:
    """What an indexing run did."""

    meeting_id: str
    materials: int
    chunks: int
    vectors: int

    def __str__(self) -> str:
        return (
            f"{self.meeting_id}: {self.materials} materials, "
            f"{self.chunks} chunks, {self.vectors} vectors"
        )


@dataclass(frozen=True)
class IndexHealth:
    """How far a meeting's index has drifted from its chunk store."""

    meeting_id: str
    stored: int
    indexed: int
    missing: list[int]
    """Chunk ids in the store with no vector. Unsearchable text."""
    orphaned: list[int]
    """Vector ids with no chunk row. These are what `strict=True` raises on."""

    @property
    def healthy(self) -> bool:
        return not self.missing and not self.orphaned


def open_index(meeting_id: str, settings: Settings | None = None) -> VectorIndex:
    """Open (or start) the vector index for one meeting."""
    resolved = settings or get_settings()
    return VectorIndex.open(
        resolved.index_path(meeting_id), resolved.embedding_dim
    )


def index_material(
    db: Database,
    material_id: str,
    *,
    embedder: Embedder | None = None,
    settings: Settings | None = None,
) -> list[int]:
    """Chunk, embed and index one material. Returns the new chunk ids.

    Safe to call repeatedly on the same material: the previous chunk rows and
    their vectors are both replaced, so re-ingesting a document does not leave
    a shadow copy of the old text in the index.
    """
    resolved = settings or get_settings()
    embedder = embedder or get_embedder(resolved)

    material = db.get_material(material_id)
    if material is None:
        raise StorageError(f"Cannot index: no material with id '{material_id}'.")

    superseded = [chunk.id for chunk in db.get_chunks_for_material(material_id)]
    new_chunks = chunk_document(material.text, settings=resolved)
    vectors = embedder.encode([chunk.text for chunk in new_chunks])

    chunk_ids = db.replace_chunks(material_id, new_chunks)

    index = open_index(material.meeting_id, resolved)
    index.remove(superseded)
    index.add(chunk_ids, vectors)
    index.save()

    logger.info(
        "Indexed material %s: %d chunks (replacing %d)",
        material_id,
        len(chunk_ids),
        len(superseded),
    )
    return chunk_ids


def delete_material_everywhere(
    db: Database, material_id: str, *, settings: Settings | None = None
) -> bool:
    """Delete a material, its chunk rows and its vectors. Returns whether it existed.

    Deleting through the repository alone cascades the chunk rows away but
    leaves the vectors behind, because SQLite cannot reach into a FAISS file.
    Those orphans are detectable and `ensure_meeting_indexed` repairs them, but
    only on the next retrieval — this removes them at the point of deletion so
    the index does not carry a deleted document's weight in the meantime.
    """
    resolved = settings or get_settings()

    material = db.get_material(material_id)
    if material is None:
        return False

    doomed = [chunk.id for chunk in db.get_chunks_for_material(material_id)]
    deleted = db.delete_material(material_id)
    if not deleted:
        return False

    if doomed:
        index = open_index(material.meeting_id, resolved)
        index.remove(doomed)
        index.save()
    logger.info(
        "Deleted material %s with its %d chunks and vectors", material_id, len(doomed)
    )
    return True


def rebuild_meeting_index(
    db: Database,
    meeting_id: str,
    *,
    embedder: Embedder | None = None,
    settings: Settings | None = None,
) -> IndexReport:
    """Re-chunk every material in a meeting and rebuild its index from zero.

    This is the backfill, and it is also the repair of last resort. The index
    is reset rather than updated in place so that vectors belonging to
    materials that have since been deleted cannot survive the rebuild.
    """
    resolved = settings or get_settings()
    embedder = embedder or get_embedder(resolved)

    materials = db.iter_material_texts(meeting_id)
    index = open_index(meeting_id, resolved)
    index.reset()

    total_chunks = 0
    for material in materials:
        new_chunks = chunk_document(material.text, settings=resolved)
        vectors = embedder.encode([chunk.text for chunk in new_chunks])
        chunk_ids = db.replace_chunks(material.id, new_chunks)
        index.add(chunk_ids, vectors)
        total_chunks += len(chunk_ids)

    index.save()
    report = IndexReport(meeting_id, len(materials), total_chunks, index.ntotal)
    logger.info("Rebuilt index for %s", report)
    return report


def reindex_from_store(
    db: Database,
    meeting_id: str,
    *,
    embedder: Embedder | None = None,
    settings: Settings | None = None,
) -> IndexReport:
    """Rebuild the index from the chunk rows, keeping their existing ids.

    Used when the index file is missing, unreadable or has drifted, but the
    chunk store itself is sound. Re-chunking in that situation would be wrong:
    it would hand every span a new id and invalidate any `chunk_id` already
    cited in a stored brief.
    """
    resolved = settings or get_settings()
    embedder = embedder or get_embedder(resolved)

    chunks = db.get_chunks_for_meeting(meeting_id)
    index = open_index(meeting_id, resolved)
    index.reset()

    if chunks:
        vectors = embedder.encode([chunk.text for chunk in chunks])
        index.add([chunk.id for chunk in chunks], vectors)
    index.save()

    materials = len({chunk.material_id for chunk in chunks})
    report = IndexReport(meeting_id, materials, len(chunks), index.ntotal)
    logger.info("Reindexed from chunk store for %s", report)
    return report


def check_index(
    db: Database, meeting_id: str, *, settings: Settings | None = None
) -> IndexHealth:
    """Compare a meeting's index against its chunk store.

    Cheap enough to run before a retrieval and precise enough to say which of
    the two sides is behind, which is the difference between "reindex" and
    "re-ingest".
    """
    resolved = settings or get_settings()
    stored = set(db.chunk_ids_for_meeting(meeting_id))
    indexed = open_index(meeting_id, resolved).ids()

    return IndexHealth(
        meeting_id=meeting_id,
        stored=len(stored),
        indexed=len(indexed),
        missing=sorted(stored - indexed),
        orphaned=sorted(indexed - stored),
    )


def ensure_meeting_indexed(
    db: Database,
    meeting_id: str,
    *,
    embedder: Embedder | None = None,
    settings: Settings | None = None,
) -> IndexReport | None:
    """Bring a meeting to a searchable state, doing the least work that works.

    Returns the repair that was performed, or `None` if nothing was needed.

    Three cases, in order of severity:

    * The meeting has materials but no chunk rows — it was ingested before the
      chunk store existed. Re-chunk it.
    * The store and index disagree — re-embed the stored chunks under their own
      ids, which fixes both missing vectors and orphaned ones.
    * They agree — do nothing.

    Retrieval calls this rather than assuming, because the alternative is a
    search that silently returns nothing on a meeting whose documents are
    sitting right there in the database.
    """
    resolved = settings or get_settings()
    health = check_index(db, meeting_id, settings=resolved)

    if health.stored == 0:
        if not db.get_materials(meeting_id):
            return None
        logger.info(
            "Meeting %s has materials but no chunks; chunking now", meeting_id
        )
        return rebuild_meeting_index(
            db, meeting_id, embedder=embedder, settings=resolved
        )

    if not health.healthy:
        logger.warning(
            "Index for %s is out of sync (%d unindexed chunks, %d orphaned "
            "vectors); rebuilding from the chunk store",
            meeting_id,
            len(health.missing),
            len(health.orphaned),
        )
        return reindex_from_store(
            db, meeting_id, embedder=embedder, settings=resolved
        )

    return None


def drop_meeting_index(meeting_id: str, settings: Settings | None = None) -> bool:
    """Delete a meeting's index file. Returns whether one existed."""
    return open_index(meeting_id, settings).delete_file()
