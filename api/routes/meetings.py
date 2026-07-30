"""Meetings: the top-level thing everything else hangs off."""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from api import deps
from api.schemas import MeetingCreate, MeetingOut
from core.exceptions import MeetingNotFoundError
from core.indexing import drop_meeting_index

router = APIRouter(prefix="/api/meetings", tags=["meetings"])


def _join(values: list[str]) -> str | None:
    """Render a list back into the comma-joined column the table stores.

    The wire format uses arrays because that is what the UI wants; the schema
    has held one `TEXT` column since before this overhaul and migrating it is
    not worth the risk for a field nothing queries on.
    """
    cleaned = [value.strip() for value in values if value.strip()]
    return ", ".join(cleaned) if cleaned else None


@router.get("", response_model=list[MeetingOut])
def list_meetings() -> list[MeetingOut]:
    db = deps.database()
    # Two grouped queries rather than two per meeting.
    materials = db.material_counts()
    briefs = db.brief_counts()
    return [
        MeetingOut.of(
            meeting,
            materials=materials.get(meeting.id, 0),
            briefs=briefs.get(meeting.id, 0),
        )
        for meeting in db.list_meetings()
    ]


@router.post("", response_model=MeetingOut, status_code=status.HTTP_201_CREATED)
def create_meeting(payload: MeetingCreate) -> MeetingOut:
    db = deps.database()
    meeting_id = db.create_meeting(
        title=payload.title,
        date=payload.date or None,
        attendees=_join(payload.attendees),
        tags=_join(payload.tags),
    )
    return MeetingOut.of(db.require_meeting(meeting_id))


@router.get("/{meeting_id}", response_model=MeetingOut)
def get_meeting(meeting_id: str) -> MeetingOut:
    db = deps.database()
    # `require_meeting` raises `MeetingNotFoundError`, which the handler in
    # `api.errors` turns into a 404. No `if is None` needed anywhere below.
    meeting = db.require_meeting(meeting_id)
    return MeetingOut.of(
        meeting,
        materials=len(db.get_materials(meeting_id)),
        briefs=len(db.get_brief_history(meeting_id)),
    )


@router.delete("/{meeting_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_meeting(meeting_id: str) -> Response:
    """Delete a meeting, its materials, briefs, chunks and vector index."""
    db = deps.database()
    db.require_meeting(meeting_id)

    # Under the lock: `delete_meeting` cascades the chunk rows away, and the
    # index file has to go with them. A concurrent recall on this meeting would
    # otherwise rebuild the index from rows that are being deleted underneath it.
    with deps.meeting_lock(meeting_id):
        deleted = db.delete_meeting(meeting_id)
        if deleted:
            drop_meeting_index(meeting_id, deps.settings())

    if not deleted:
        # It existed at `require_meeting` and does not now, so another request
        # removed it in between. Reporting 404 is the honest answer.
        raise MeetingNotFoundError(meeting_id)

    return Response(status_code=status.HTTP_204_NO_CONTENT)
