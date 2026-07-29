"""Asking questions about one meeting's materials."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from api import deps
from api.schemas import QaRequest, QaResponse
from api.translate import qa_response

router = APIRouter(prefix="/api", tags=["qa"])


@router.post("/meetings/{meeting_id}/qa", response_model=QaResponse)
def ask(meeting_id: str, payload: QaRequest) -> QaResponse:
    """Answer one question.

    The graph answers "I could not find relevant information" without calling
    the model when nothing was retrieved, which is a successful run and comes
    back `ok=True`. A retrieval *failure* lands on the same node, so
    `api.translate.qa_response` reports `ok=False` whenever an error is set —
    otherwise a broken index would read as a polite non-answer.
    """
    db = deps.database()
    db.require_meeting(meeting_id)

    if not db.get_materials(meeting_id):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Upload at least one document before asking questions.",
        )

    # Retrieval writes the index when it backfills, so this takes the same lock
    # brief generation and ingestion do.
    with deps.meeting_lock(meeting_id):
        result = deps.orchestrator().answer_question(
            meeting_id=meeting_id, question=payload.question
        )

    return qa_response(result)
