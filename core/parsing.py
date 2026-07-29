"""Document parsing for PDF, DOCX, PPTX, and TXT files.

Every parser returns `""` rather than raising when a file cannot be read. That
is deliberate and it is the caller's job to notice: `CopilotOrchestrator.
ingest_material` treats empty text as a failed ingestion and says so, so a
corrupt upload is reported once, in the UI, instead of twice — as a traceback
here and as a mysteriously empty material there.

What *was* lost is the reason. `log_message("ERROR", f"...: {e}")` recorded the
exception's `str()` and dropped the traceback, so "Failed to parse PDF: " with
an empty message was a common and useless log line. `logger.exception` keeps
the traceback.

`parse_pasted_text` used to live here. Pasted text now arrives through
`parse_file` as a `.txt` upload, with `media_type="pasted"` supplied by the
caller, so there is one path in and it is the one with tests behind it.
"""

from __future__ import annotations

import io

from core.logging_config import get_logger

logger = get_logger(__name__)


def parse_pdf(file_content: bytes) -> str:
    """Extract text from PDF file."""
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(file_content))
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
        logger.info("Parsed PDF: %d characters", len(text))
        return text.strip()
    except Exception:
        logger.exception("Failed to parse PDF")
        return ""


def parse_docx(file_content: bytes) -> str:
    """Extract text from DOCX file."""
    try:
        from docx import Document
        doc = Document(io.BytesIO(file_content))
        text = "\n".join([para.text for para in doc.paragraphs])
        logger.info("Parsed DOCX: %d characters", len(text))
        return text.strip()
    except Exception:
        logger.exception("Failed to parse DOCX")
        return ""


def parse_pptx(file_content: bytes) -> str:
    """Extract text from PPTX file."""
    try:
        from pptx import Presentation
        prs = Presentation(io.BytesIO(file_content))
        text = ""
        for slide in prs.slides:
            for shape in slide.shapes:
                if hasattr(shape, "text"):
                    text += shape.text + "\n"
        logger.info("Parsed PPTX: %d characters", len(text))
        return text.strip()
    except Exception:
        logger.exception("Failed to parse PPTX")
        return ""


def parse_txt(file_content: bytes) -> str:
    """Extract text from TXT file."""
    try:
        text = file_content.decode("utf-8", errors="ignore").strip()
        logger.info("Parsed TXT: %d characters", len(text))
        return text
    except Exception:
        logger.exception("Failed to parse TXT")
        return ""


def parse_file(file_content: bytes, filename: str) -> tuple[str, str]:
    """
    Parse a file based on its extension.
    Returns (text, media_type).
    """
    filename_lower = filename.lower()

    if filename_lower.endswith(".pdf"):
        return parse_pdf(file_content), "pdf"
    elif filename_lower.endswith(".docx"):
        return parse_docx(file_content), "docx"
    elif filename_lower.endswith(".pptx"):
        return parse_pptx(file_content), "pptx"
    elif filename_lower.endswith(".txt"):
        return parse_txt(file_content), "txt"
    else:
        logger.warning("Unsupported file type: %s", filename)
        return "", "unknown"
