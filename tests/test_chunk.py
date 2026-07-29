"""Chunking: offsets must describe where the text actually came from."""

from __future__ import annotations

from itertools import pairwise

import pytest

from core.chunk import chunk_document
from core.config import Settings


@pytest.fixture
def small(settings: Settings) -> Settings:
    """Chunk sizes small enough to exercise the loop on readable fixtures."""
    return settings.model_copy(update={"chunk_size": 60, "chunk_overlap": 15})


def test_every_chunk_can_be_sliced_back_out_of_the_source(small: Settings):
    """The invariant the whole citation story rests on."""
    text = (
        "Revenue grew by twelve percent this quarter.\n\n"
        "Marketing overspent its budget by a wide margin, again.\n\n"
        "Hiring is paused until the board reviews the runway forecast.\n\n"
        "Legal flagged two open items in the vendor agreement."
    )

    chunks = chunk_document(text, settings=small)

    assert chunks
    for chunk in chunks:
        assert text[chunk.char_start : chunk.char_end] == chunk.text


def test_offsets_survive_leading_and_trailing_whitespace(small: Settings):
    """The original code stripped the slice and lost the correspondence.

    Whitespace is trimmed from the *offsets*, so a chunk that begins after a
    blank line still points at its own first character.
    """
    text = "\n\n   Opening statement here.\n\n\n\n   Second paragraph follows.   \n\n"

    chunks = chunk_document(text, settings=small)

    for chunk in chunks:
        assert not chunk.text.startswith((" ", "\n"))
        assert not chunk.text.endswith((" ", "\n"))
        assert text[chunk.char_start : chunk.char_end] == chunk.text


def test_chunks_are_indexed_in_document_order(small: Settings):
    text = "\n\n".join(f"Paragraph number {n} of the document body." for n in range(8))

    chunks = chunk_document(text, settings=small)

    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
    assert [c.char_start for c in chunks] == sorted(c.char_start for c in chunks)


def test_consecutive_chunks_overlap(small: Settings):
    text = "word " * 200

    chunks = chunk_document(text, settings=small)

    assert len(chunks) > 2
    for previous, following in pairwise(chunks):
        assert following.char_start < previous.char_end


def test_the_whole_document_is_covered(small: Settings):
    """No span of non-whitespace text may fall between two chunks."""
    text = "\n\n".join(f"Sentence {n} carries some distinct content." for n in range(20))

    chunks = chunk_document(text, settings=small)

    assert chunks[0].char_start == 0
    assert chunks[-1].char_end == len(text.rstrip())
    for previous, following in pairwise(chunks):
        assert following.char_start <= previous.char_end


def test_a_short_document_is_one_chunk(small: Settings):
    text = "Just a line."

    chunks = chunk_document(text, settings=small)

    assert len(chunks) == 1
    assert chunks[0].text == text
    assert (chunks[0].char_start, chunks[0].char_end) == (0, len(text))


@pytest.mark.parametrize("extra", [-1, 0, 1, 5, 30, 61])
def test_no_chunk_is_wholly_contained_in_another(small: Settings, extra: int):
    """Every chunk must carry text no other chunk already has.

    Stepping back by the overlap after reaching the end of a document produces
    a final chunk made entirely of the tail of the previous one — redundant
    text that then competes with its own source in search results.
    """
    text = "x" * (small.chunk_size + extra)

    chunks = chunk_document(text, settings=small)

    spans = [(c.char_start, c.char_end) for c in chunks]
    for start, end in spans:
        containers = [s for s in spans if s != (start, end) and s[0] <= start and end <= s[1]]
        assert not containers, f"span {(start, end)} is contained in {containers}"


def test_empty_and_blank_documents_produce_nothing(small: Settings):
    assert chunk_document("", settings=small) == []
    assert chunk_document("   \n\n  \t ", settings=small) == []


def test_paragraph_boundaries_are_preferred_to_arbitrary_cuts(small: Settings):
    text = "First paragraph, complete and tidy.\n\n" + "tail " * 40

    chunks = chunk_document(text, settings=small)

    assert chunks[0].text == "First paragraph, complete and tidy."


def test_overlap_must_be_smaller_than_the_chunk(settings: Settings):
    with pytest.raises(ValueError, match="must be smaller"):
        chunk_document("some text", chunk_size=100, chunk_overlap=100, settings=settings)


def test_chunk_size_defaults_come_from_settings(settings: Settings):
    """900/150, chosen so chunks fit inside what the embedder actually reads."""
    text = "sentence. " * 500

    chunks = chunk_document(text, settings=settings)

    assert max(len(c.text) for c in chunks) <= settings.chunk_size
