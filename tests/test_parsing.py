"""Extraction, dispatch, and the contract that a bad file returns "".

The parsers were the last module still logging through `core.utils.log_message`,
and they had no tests at all. Both facts are fixed here, because the thing worth
pinning is not the logging: it is that a parser which cannot read its input
returns an empty string instead of raising, and that `ingest_material` is
therefore the single place a failed upload is reported.
"""

from __future__ import annotations

import io
import logging

import pytest

from core.parsing import parse_docx, parse_file, parse_pdf, parse_pptx, parse_txt


def test_txt_is_decoded_and_stripped():
    assert parse_txt(b"  hello there  \n") == "hello there"


def test_txt_survives_bytes_that_are_not_utf8():
    """`errors="ignore"`: a mangled byte costs a character, not the document."""
    assert parse_txt("café".encode("latin-1")) == "caf"


@pytest.mark.parametrize(
    ("filename", "media_type"),
    [
        ("notes.txt", "txt"),
        ("NOTES.TXT", "txt"),
        ("deck.pptx", "pptx"),
        ("report.docx", "docx"),
        ("transcript.pdf", "pdf"),
    ],
)
def test_parse_file_dispatches_on_the_extension_case_insensitively(
    filename: str, media_type: str
):
    _, detected = parse_file(b"", filename)
    assert detected == media_type


def test_an_unsupported_extension_is_reported_not_guessed_at():
    text, media_type = parse_file(b"MZ\x90\x00", "installer.exe")

    assert text == ""
    assert media_type == "unknown"


@pytest.mark.parametrize("parser", [parse_pdf, parse_docx, parse_pptx])
def test_an_unreadable_file_returns_empty_text_rather_than_raising(parser):
    """`ingest_material` turns this into "no readable text", once, in the UI."""
    assert parser(b"this is not a document") == ""


def test_the_failure_is_logged_with_its_traceback(caplog: pytest.LogCaptureFixture):
    """`log_message` recorded `str(exc)`, which is often empty. This does not."""
    with caplog.at_level(logging.ERROR, logger="core.parsing"):
        parse_pdf(b"not a pdf")

    record = caplog.records[-1]
    assert record.exc_info is not None
    assert "Failed to parse PDF" in record.getMessage()


def test_a_real_docx_round_trips():
    """One genuine document, so the happy path is not only asserted in the negative."""
    docx = pytest.importorskip("docx")

    document = docx.Document()
    document.add_paragraph("Budget forecast")
    document.add_paragraph("Hiring plan")
    buffer = io.BytesIO()
    document.save(buffer)

    assert parse_docx(buffer.getvalue()) == "Budget forecast\nHiring plan"
