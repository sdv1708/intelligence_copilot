"""Uploading, listing and deleting the documents a brief is built from."""

from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, Response, UploadFile, status

from api import deps
from api.schemas import IngestOutcome, IngestResponse, MaterialOut, PasteRequest
from core.indexing import delete_material_everywhere
from core.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["materials"])

# Per file, not per request. The parsers load the whole document into memory and
# the biggest thing in `data/` today is a 268k-character transcript, so this is
# generous rather than tight — it exists to stop a mistake, not to ration.
MAX_UPLOAD_BYTES = 25 * 1024 * 1024


@router.get("/meetings/{meeting_id}/materials", response_model=list[MaterialOut])
def list_materials(meeting_id: str) -> list[MaterialOut]:
    db = deps.database()
    db.require_meeting(meeting_id)
    return [MaterialOut.of(material) for material in db.get_materials(meeting_id)]


@router.post("/meetings/{meeting_id}/materials", response_model=IngestResponse)
async def upload_materials(
    meeting_id: str, files: list[UploadFile] = File(...)
) -> IngestResponse:
    """Ingest one or more uploaded files.

    Deliberately not all-or-nothing. A corrupt PDF alongside three good decks
    should cost you the PDF, so every file reports its own outcome and the
    response carries the failures rather than a single error for the batch.

    `ingest_material` is one call that parses, stores, chunks, embeds and
    indexes. There is no way to reach it that stores a document without also
    indexing it — the pre-overhaul UI did those as two steps, so a file whose
    indexing failed was still listed as a material and then silently never
    searched.
    """
    deps.database().require_meeting(meeting_id)
    orchestrator = deps.orchestrator()

    outcomes: list[IngestOutcome] = []
    for upload in files:
        name = upload.filename or "untitled"
        # `await` outside the lock: reading the request body is I/O and holding
        # a meeting's index lock across it would serialize uploads on the
        # network rather than on the index.
        payload = await upload.read()

        if len(payload) > MAX_UPLOAD_BYTES:
            outcomes.append(
                IngestOutcome(
                    filename=name,
                    success=False,
                    error=(
                        f"'{name}' is {len(payload) / 1_048_576:.1f} MB, over the "
                        f"{MAX_UPLOAD_BYTES // 1_048_576} MB limit."
                    ),
                )
            )
            continue

        with deps.meeting_lock(meeting_id):
            result = orchestrator.ingest_material(
                file_bytes=payload, filename=name, meeting_id=meeting_id
            )

        outcomes.append(
            IngestOutcome(
                filename=name,
                success=bool(result.get("success")),
                material_id=result.get("material_id"),
                chunks=result.get("chunks", 0),
                characters=result.get("characters", 0),
                error=result.get("error"),
            )
        )

    ingested = sum(1 for outcome in outcomes if outcome.success)
    return IngestResponse(
        results=outcomes, ingested=ingested, failed=len(outcomes) - ingested
    )


@router.post("/meetings/{meeting_id}/materials/text", response_model=IngestOutcome)
def paste_material(meeting_id: str, payload: PasteRequest) -> IngestOutcome:
    """Ingest pasted text as if it were an uploaded `.txt`.

    `media_type="pasted"` overrides what the extension would imply, so the
    materials list can distinguish a pasted note from an uploaded text file.
    """
    deps.database().require_meeting(meeting_id)

    with deps.meeting_lock(meeting_id):
        result = deps.orchestrator().ingest_material(
            file_bytes=payload.text.encode("utf-8"),
            filename=payload.filename,
            meeting_id=meeting_id,
            media_type="pasted",
        )

    return IngestOutcome(
        filename=payload.filename,
        success=bool(result.get("success")),
        material_id=result.get("material_id"),
        chunks=result.get("chunks", 0),
        characters=result.get("characters", 0),
        error=result.get("error"),
    )


@router.delete("/materials/{material_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_material(material_id: str) -> Response:
    """Delete a material along with its chunk rows and its vectors.

    Deleting through the repository alone would cascade the rows away and leave
    the vectors behind, so the document would keep turning up in search until
    the next retrieval repaired the index.
    """
    db = deps.database()
    material = db.get_material(material_id)
    if material is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No material found with id '{material_id}'.",
        )

    with deps.meeting_lock(material.meeting_id):
        delete_material_everywhere(db, material_id, settings=deps.settings())

    return Response(status_code=status.HTTP_204_NO_CONTENT)
