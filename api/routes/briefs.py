"""Generating, recalling and listing briefs."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import ValidationError

from api import deps
from api.schemas import BriefResponse, BriefStub
from api.translate import brief_response
from core.exceptions import InvalidBriefError

router = APIRouter(prefix="/api", tags=["briefs"])


@router.post("/meetings/{meeting_id}/brief", response_model=BriefResponse)
def generate_brief(meeting_id: str) -> BriefResponse:
    """Run the brief graph for one meeting.

    This holds the meeting's lock for the whole run — tens of seconds. That is
    deliberate rather than an oversight: the graph's retrieval step writes the
    index through `ensure_meeting_indexed`, so an upload landing mid-run would
    be racing it. Other meetings are unaffected.
    """
    db = deps.database()
    meeting = db.require_meeting(meeting_id)

    if not db.get_materials(meeting_id):
        # A precondition, not a run outcome. Letting the graph discover this
        # would cost a planning round-trip to reach the same conclusion, and
        # would report it as a failed run rather than as "you haven't uploaded
        # anything yet".
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Upload at least one document before generating a brief.",
        )

    with deps.meeting_lock(meeting_id):
        result = deps.orchestrator().generate_brief(
            meeting_id=meeting_id,
            title=meeting.title,
            date=meeting.date or "Today",
        )

    response = brief_response(result)

    # The run knows the id it was stored under but not when — `created_at` is
    # written by the database. Without this a brief that *did* store comes back
    # with `stored_at: null`, which is the value that means "not stored", and
    # every client would read a successful save as a failed one.
    if response.brief_id:
        record = db.get_brief_by_id(response.brief_id)
        if record is not None:
            response.stored_at = record.created_at

    return response


@router.get("/meetings/{meeting_id}/briefs", response_model=list[BriefStub])
def brief_history(meeting_id: str) -> list[BriefStub]:
    db = deps.database()
    db.require_meeting(meeting_id)
    return [
        BriefStub(
            id=summary.id,
            meeting_id=summary.meeting_id,
            created_at=summary.created_at,
            model=summary.model or "unknown",
        )
        for summary in db.get_brief_history(meeting_id)
    ]


@router.get("/meetings/{meeting_id}/brief/latest", response_model=BriefResponse)
def latest_brief(meeting_id: str) -> BriefResponse:
    """The most recent stored brief for a meeting.

    404 when there is none. `recall_previous_brief` raises `InvalidBriefError`
    when the stored payload no longer satisfies the current schema, which the
    handler reports as 422 — a row written before a schema change is a real and
    different situation from no brief at all, and saying "none found" would
    hide it.
    """
    db = deps.database()
    db.require_meeting(meeting_id)

    brief = deps.orchestrator().recall_previous_brief(meeting_id)
    if brief is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No brief has been generated for this meeting yet.",
        )

    record = db.get_latest_brief(meeting_id)
    return BriefResponse(
        ok=True,
        brief=brief,
        brief_id=record.id if record else None,
        model=(record.model if record else None) or "",
        # A brief read back from storage has no run behind it, so there is no
        # trace to show. `None` rather than an empty `Trace` so the UI can tell
        # "recalled" from "generated with an empty trace".
        trace=None,
        stored_at=record.created_at if record else None,
    )


@router.get("/briefs/{brief_id}", response_model=BriefResponse)
def get_brief(brief_id: str) -> BriefResponse:
    """One stored brief by id, for the history list."""
    record = deps.database().get_brief_by_id(brief_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No brief found with id '{brief_id}'.",
        )

    # `as_brief` validates the stored payload against today's schema and raises
    # a plain `ValidationError` if it does not fit. Briefs are written once and
    # read for years, so that is a live possibility rather than a theoretical
    # one; `InvalidBriefError` names it and the handler maps it to 422.
    try:
        brief = record.as_brief()
    except ValidationError as error:
        raise InvalidBriefError(
            f"Stored brief {record.id} does not satisfy the current schema: {error}"
        ) from error

    return BriefResponse(
        ok=True,
        brief=brief,
        brief_id=record.id,
        model=record.model or "",
        trace=None,
        stored_at=record.created_at,
    )
