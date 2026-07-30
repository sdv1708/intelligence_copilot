"""Request and response bodies.

These exist rather than returning `core.schema` records directly because the two
have different jobs. A `Material` carries its full text — a 268k-character
transcript that no list view wants — and a `Meeting` stores attendees as one
comma-joined string because that is how the column was written years ago. The
wire format splits those into arrays and drops the bodies.

`MeetingBrief` is the exception: it is already the shape the UI renders, it is
already validated, and re-declaring it here would mean two definitions of a
brief drifting apart. It is re-exported and used as-is.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from core.schema import MaterialSummary, Meeting, MeetingBrief

__all__ = [
    "BriefResponse",
    "BriefStub",
    "FindingOut",
    "Health",
    "IngestOutcome",
    "IngestResponse",
    "MaterialOut",
    "MeetingBrief",
    "MeetingCreate",
    "MeetingOut",
    "PasteRequest",
    "QaRequest",
    "QaResponse",
    "TaskOut",
    "Trace",
]


class Out(BaseModel):
    """Base for everything sent to the browser."""

    model_config = ConfigDict(extra="forbid")


# --- Meetings ---------------------------------------------------------------


class MeetingCreate(BaseModel):
    """A new meeting, as the composer posts it."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=300)
    date: str | None = Field(default=None, max_length=32)
    attendees: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class MeetingOut(Out):
    """A meeting as the sidebar lists it."""

    id: str
    title: str
    date: str | None
    attendees: list[str]
    tags: list[str]
    created_at: str
    material_count: int = 0
    brief_count: int = 0

    @classmethod
    def of(cls, meeting: Meeting, *, materials: int = 0, briefs: int = 0) -> MeetingOut:
        return cls(
            id=meeting.id,
            title=meeting.title,
            date=meeting.date,
            # `attendee_list` and `tag_list` do the comma splitting, so the
            # storage format stays a detail of the record type.
            attendees=meeting.attendee_list,
            tags=meeting.tag_list,
            created_at=meeting.created_at,
            material_count=materials,
            brief_count=briefs,
        )


# --- Materials --------------------------------------------------------------


class MaterialOut(Out):
    """One indexed document, without its text."""

    id: str
    meeting_id: str
    filename: str
    media_type: str
    char_count: int
    created_at: str

    @classmethod
    def of(cls, material: MaterialSummary) -> MaterialOut:
        return cls(
            id=material.id,
            meeting_id=material.meeting_id,
            # Both columns are nullable and real rows in `data/briefs.db` have
            # them null. Substituting here means no client has to.
            filename=material.filename or "Untitled",
            media_type=material.media_type or "unknown",
            char_count=material.char_count,
            created_at=material.created_at,
        )


class PasteRequest(BaseModel):
    """Text pasted into the UI rather than uploaded as a file."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1)
    filename: str = Field(default="pasted_text.txt", min_length=1, max_length=255)


class IngestOutcome(Out):
    """What happened to one uploaded file.

    A multi-file upload is not all-or-nothing: a corrupt PDF alongside three
    good ones should cost you the PDF. Each file reports its own result and the
    UI lists the failures.
    """

    filename: str
    success: bool
    material_id: str | None = None
    chunks: int = 0
    characters: int = 0
    error: str | None = None


class IngestResponse(Out):
    results: list[IngestOutcome]
    ingested: int
    failed: int


# --- The trace --------------------------------------------------------------


class TaskOut(Out):
    """One line of enquiry the supervisor decided to run."""

    name: str
    query: str
    rationale: str
    is_sweep: bool


class FindingOut(Out):
    """What one specialist came back with.

    `hits` and `neighbours` are separated because they mean different things:
    a hit matched the query, a neighbour was pulled in for context because it
    sits beside one. Collapsing them into a single count would overstate how
    much the search actually found.
    """

    name: str
    query: str
    ok: bool
    hits: int
    neighbours: int
    error: str | None = None


class Trace(Out):
    """How a result was produced.

    This is the part the old Streamlit UI could only render as a wall of
    monospace text in a collapsed expander. It is a first-class part of the
    response because a thin brief is worth explaining rather than guessing at.
    """

    notes: list[str] = Field(default_factory=list)
    plan: list[TaskOut] = Field(default_factory=list)
    plan_source: str = ""
    plan_rationale: str = ""
    findings: list[FindingOut] = Field(default_factory=list)
    chunks: int = 0


# --- Briefs -----------------------------------------------------------------


class BriefStub(Out):
    """A row of the brief history, without the payload."""

    id: str
    meeting_id: str
    created_at: str
    model: str


class BriefResponse(Out):
    """A generated or recalled brief.

    `ok` and `warning` are deliberately separate. A run that produced a brief
    and then failed to store it is `ok=True` with a `warning`, because throwing
    away a usable document because SQLite was locked serves nobody. A client
    that only reads `ok` gets the document; one that reads `warning` can also
    say what went wrong.
    """

    ok: bool
    brief: MeetingBrief | None = None
    brief_id: str | None = None
    provider: str = ""
    model: str = ""
    warning: str | None = None
    failed_tasks: list[str] = Field(default_factory=list)
    trace: Trace | None = None
    stored_at: str | None = None


# --- Q&A --------------------------------------------------------------------


class QaRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    question: str = Field(min_length=1, max_length=2000)


class QaResponse(Out):
    ok: bool
    answer: str = ""
    sources: list[str] = Field(default_factory=list)
    provider: str = ""
    model: str = ""
    error: str | None = None
    trace: Trace | None = None


# --- Status -----------------------------------------------------------------


class Health(Out):
    """What the status line reports.

    `storage_is_temporary` exists because `Settings.prepare_storage` silently
    relocates to a temp directory when the configured one is unwritable, and a
    user whose data will not survive a restart should be told.
    """

    provider: str
    model: str
    device: str
    supervisor: bool
    has_api_key: bool
    storage_dir: str
    storage_is_temporary: bool
