"""Split a document into embeddable spans that remember where they came from.

Two things changed from the original `chunk_text`, and both matter:

* **Chunks carry byte-exact offsets.** Every chunk records the `char_start` /
  `char_end` of the span it was cut from, and the invariant
  `material_text[chunk.char_start:chunk.char_end] == chunk.text` holds for every
  chunk this module produces. The old implementation stripped each chunk after
  slicing, which is why offsets could not simply be computed afterwards --
  leading whitespace would push the text out of alignment with its own
  coordinates. Trimming happens to the *offsets* here, and the text is sliced
  from the trimmed span, so the two can never disagree.

* **Chunks are small again.** `all-MiniLM-L6-v2` truncates at 256 word-pieces,
  roughly 1000 characters. The 4000-character chunks the previous version
  produced had about three quarters of their content silently invisible to the
  embedder, so search matched on the opening paragraph and nothing else. The
  defaults now come from `settings.chunk_size` / `chunk_overlap` (900/150), and
  the breadth that larger chunks were reaching for is restored at retrieval
  time by neighbour expansion instead.

Offsets are not decoration. They are what makes it possible to show a citation
in context, to re-derive a chunk from the material it belongs to, and to check
that a stored chunk still matches its source.
"""

from __future__ import annotations

from core.config import Settings, get_settings
from core.logging_config import get_logger
from core.schema import NewChunk

logger = get_logger(__name__)

# A boundary is only worth cutting on if it lands at least this far into the
# window. Otherwise a stray "\n\n" near the start of a long paragraph would
# produce a sliver of a chunk and waste most of the window.
_MIN_FILL = 0.5

# Ordered by preference: a paragraph break is a better place to cut than a
# sentence end, which is better than an arbitrary character.
_SEPARATORS: tuple[str, ...] = ("\n\n", ". ", ".\n", "\n")


def chunk_document(
    text: str,
    *,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
    settings: Settings | None = None,
) -> list[NewChunk]:
    """Cut `text` into overlapping `NewChunk`s with exact source offsets.

    Chunks are indexed from zero in document order and never empty. Whitespace
    between chunks is dropped from the *edges* of each span, so the offsets
    stay valid coordinates into `text`.
    """
    if not text:
        return []

    resolved = settings or get_settings()
    size = chunk_size if chunk_size is not None else resolved.chunk_size
    overlap = chunk_overlap if chunk_overlap is not None else resolved.chunk_overlap

    if size <= 0:
        raise ValueError(f"chunk_size must be positive, got {size}")
    if overlap >= size:
        raise ValueError(
            f"chunk_overlap ({overlap}) must be smaller than chunk_size ({size}); "
            "otherwise chunking cannot advance through the document."
        )

    chunks: list[NewChunk] = []
    length = len(text)
    start = 0

    while start < length:
        window_end = min(length, start + size)
        cut = window_end if window_end >= length else _find_cut(text, start, window_end, size)

        span_start, span_end = _trim(text, start, cut)
        if span_end > span_start:
            chunks.append(
                NewChunk(
                    chunk_index=len(chunks),
                    text=text[span_start:span_end],
                    char_start=span_start,
                    char_end=span_end,
                )
            )

        if cut >= length:
            # Reached the end of the document. Stepping back by `overlap` here
            # would emit a final chunk wholly contained in the previous one.
            break

        # `start + 1` is a floor, not an expectation: it guarantees forward
        # progress even if a boundary lands where the window began.
        start = max(cut - overlap, start + 1)

    logger.debug(
        "Chunked %d characters into %d chunks (size=%d, overlap=%d)",
        length,
        len(chunks),
        size,
        overlap,
    )
    return chunks


def _find_cut(text: str, start: int, window_end: int, size: int) -> int:
    """Choose where to end a chunk that begins at `start`.

    Returns an offset in `(start, window_end]`. Prefers a natural boundary near
    the end of the window; falls back to the hard window edge.
    """
    minimum = start + int(size * _MIN_FILL)

    for separator in _SEPARATORS:
        found = text.rfind(separator, start, window_end)
        if found == -1:
            continue
        # Cut after the separator so it belongs to the chunk that it ends,
        # rather than opening the next one.
        cut = found + len(separator)
        if cut > minimum:
            return min(cut, window_end)

    return window_end


def _trim(text: str, start: int, end: int) -> tuple[int, int]:
    """Narrow `[start, end)` past surrounding whitespace.

    Trimming the coordinates rather than the sliced string is the whole point:
    `text[start:end]` after this call is exactly what a `.strip()` would have
    produced, but the offsets still describe where it lives.
    """
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end
