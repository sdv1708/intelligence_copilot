"""Mapping `core.exceptions` onto HTTP status codes.

The hierarchy in `core/exceptions.py` exists so callers can catch at the
granularity they care about. This is the one caller that cares about all of it:
without this handler every one of them is an opaque 500, and a missing API key
would be indistinguishable from a corrupt index.

The table is ordered, and **subclasses must precede their bases** — the first
match wins, so `InvalidBriefError` has to be tested before `SynthesisError` or it
would never be reached.
"""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

from core.exceptions import (
    ConfigurationError,
    CopilotError,
    EmptyDocumentError,
    IngestionError,
    InvalidBriefError,
    MeetingNotFoundError,
    RetrievalError,
    StorageError,
    SynthesisError,
    UnsupportedFileTypeError,
)
from core.logging_config import get_logger

logger = get_logger(__name__)

_STATUS: tuple[tuple[type[CopilotError], int], ...] = (
    (MeetingNotFoundError, 404),
    (UnsupportedFileTypeError, 415),
    # The file parsed but held nothing usable. That is a problem with the
    # content, not with the request, which is what 422 says.
    (EmptyDocumentError, 422),
    (IngestionError, 400),
    # A stored brief that no longer satisfies the schema, or a model that
    # returned something unusable. Not an outage — the payload is wrong.
    (InvalidBriefError, 422),
    # The upstream model failed. 502 rather than 500 so it is visibly *not* our
    # bug when a provider times out.
    (SynthesisError, 502),
    # Misconfiguration is a server state, and it is fixable by whoever runs the
    # server: no API key, unknown provider, broken prompt file.
    (ConfigurationError, 503),
    # Retrieval and storage failures are ours. `IndexOutOfSyncError` lands here
    # and should: it means the index and the chunk store disagree, which is a
    # bug rather than something the client did.
    (RetrievalError, 500),
    (StorageError, 500),
    (CopilotError, 500),
)


def status_for(error: CopilotError) -> int:
    for kind, status in _STATUS:
        if isinstance(error, kind):
            return status
    return 500


async def handle_copilot_error(request: Request, error: Exception) -> JSONResponse:
    """Report a `CopilotError` as its mapped status with the message intact."""
    assert isinstance(error, CopilotError)
    status = status_for(error)

    # Anything below 500 is the client's or the content's problem and does not
    # need a stack trace; a 5xx is ours and does.
    if status >= 500:
        logger.exception("%s %s failed", request.method, request.url.path)
    else:
        logger.info(
            "%s %s -> %d: %s", request.method, request.url.path, status, error
        )

    return JSONResponse(
        status_code=status,
        content={"detail": str(error), "kind": type(error).__name__},
    )
