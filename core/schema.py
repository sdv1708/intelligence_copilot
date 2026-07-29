"""Pydantic models for persisted rows and for the LLM-facing brief structures.

Two families live here:

* **Records** (`Meeting`, `Material`, `Chunk`, `BriefRecord`, ...) mirror rows in
  SQLite. They are frozen, and they are read by attribute: the mapping shim that
  let the un-migrated UI index them like the dicts the old repository returned
  went with the last caller.
* **Brief structures** (`MeetingBrief` and friends) are what the model is asked
  to produce. These are validated strictly, because a malformed brief is a bug
  we want surfaced at the boundary rather than rendered half-empty in the UI.
"""

from __future__ import annotations

import re
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# --- Record base ------------------------------------------------------------

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME_WINDOW = re.compile(r"^\d{4}-\d{2}-\d{2}\.\.\d{4}-\d{2}-\d{2}$")


class Record(BaseModel):
    """Base class for models that mirror a database row.

    Frozen, because a record is a snapshot of what was read: mutating it does
    not change the database, and code that assumed otherwise was one of the
    quieter bugs in the original implementation.
    """

    # No `str_strip_whitespace` here on purpose: a record must read back byte
    # for byte what was written. Stripping `Chunk.text` would silently
    # invalidate its `char_start`/`char_end` offsets into the material.
    model_config = ConfigDict(frozen=True, extra="forbid")


# --- Persisted records ------------------------------------------------------


class Meeting(Record):
    """A row of the `meetings` table."""

    id: str
    title: str = Field(min_length=1)
    date: str | None = None
    attendees: str | None = None
    tags: str | None = None
    created_at: str

    @property
    def attendee_list(self) -> list[str]:
        """Attendees split on commas, empties dropped."""
        return [a.strip() for a in (self.attendees or "").split(",") if a.strip()]

    @property
    def tag_list(self) -> list[str]:
        return [t.strip() for t in (self.tags or "").split(",") if t.strip()]


class Material(Record):
    """A row of the `materials` table, including its text."""

    id: str
    meeting_id: str
    filename: str | None = None
    media_type: str | None = None
    text: str
    created_at: str

    @property
    def char_count(self) -> int:
        return len(self.text)


class MaterialSummary(Record):
    """A `materials` row without the text body.

    Listing materials for the sidebar used to `SELECT LENGTH(text)` so a
    268k-character transcript was not dragged into memory to render one line of
    UI. That optimisation is worth keeping, so it gets its own type rather than
    an `Optional[str]` text field that callers have to remember to check.
    """

    id: str
    meeting_id: str
    filename: str | None = None
    media_type: str | None = None
    char_count: int = Field(ge=0)
    created_at: str


class Chunk(Record):
    """A row of the `chunks` table: one embeddable span of one material.

    `id` is the integer primary key, and it is the whole point of this table.
    FAISS `IndexIDMap2` stores an int64 alongside each vector; using this id
    means a search result maps back to exactly one row of text, forever. The
    previous design re-chunked the material at query time and trusted the
    positional order to match the index, which it did not.
    """

    id: int = Field(gt=0)
    material_id: str
    meeting_id: str
    chunk_index: int = Field(ge=0)
    text: str = Field(min_length=1)
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)
    created_at: str

    @model_validator(mode="after")
    def _check_span(self) -> Self:
        if self.char_end < self.char_start:
            raise ValueError(
                f"char_end ({self.char_end}) precedes char_start ({self.char_start})"
            )
        return self

    @property
    def source_ref(self) -> str:
        """Citation label used in prompts and in `Evidence.source`."""
        return f"{self.material_id}#c{self.chunk_index}"


class NewChunk(BaseModel):
    """A chunk on its way into the database, before an id has been assigned."""

    model_config = ConfigDict(extra="forbid")

    chunk_index: int = Field(ge=0)
    text: str = Field(min_length=1)
    char_start: int = Field(default=0, ge=0)
    char_end: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _default_span(self) -> Self:
        if self.char_end == 0:
            self.char_end = self.char_start + len(self.text)
        if self.char_end < self.char_start:
            raise ValueError(
                f"char_end ({self.char_end}) precedes char_start ({self.char_start})"
            )
        return self


class ScoredChunk(BaseModel):
    """A chunk with a retrieval score attached.

    `is_neighbour` marks a chunk pulled in because it sits next to a hit rather
    than because it matched — the prompt formatter labels those differently so
    the model is not told a filler chunk was a strong match.
    """

    model_config = ConfigDict(extra="forbid")

    chunk: Chunk
    score: float
    is_neighbour: bool = False

    @property
    def source_ref(self) -> str:
        return self.chunk.source_ref


# --- Brief structures -------------------------------------------------------


class BriefModel(BaseModel):
    """Base for the structures the LLM fills in.

    `extra="ignore"` rather than `forbid`: models routinely add a stray
    commentary key, and dropping it is better than failing a whole brief.
    """

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


class ActionItem(BriefModel):
    """A single action item carried out of a meeting."""

    owner: str = Field(min_length=1)
    item: str = Field(min_length=1)
    due: str | None = None
    status: Literal["open", "blocked", "done"] = "open"

    @field_validator("due")
    @classmethod
    def _check_due(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        value = value.strip()
        if not _ISO_DATE.match(value):
            raise ValueError(f"due must be YYYY-MM-DD, got {value!r}")
        return value

    @field_validator("status", mode="before")
    @classmethod
    def _normalise_status(cls, value: Any) -> Any:
        """Accept the casing and synonyms models actually emit."""
        if not isinstance(value, str):
            return value
        lowered = value.strip().lower()
        return {
            "": "open",
            "in progress": "open",
            "in_progress": "open",
            "pending": "open",
            "closed": "done",
            "complete": "done",
            "completed": "done",
        }.get(lowered, lowered)


class AgendaItem(BriefModel):
    """A proposed agenda line with a time box."""

    topic: str = Field(min_length=1)
    minutes: int = Field(gt=0, le=480)
    owner: str | None = None


class Evidence(BriefModel):
    """A citation tying a statement in the brief back to source text.

    `chunk_id` is populated once retrieval is keyed on chunk row ids (Chunk 3);
    `source` remains the human-readable `material_id#cN` label.
    """

    source: str = Field(min_length=1)
    snippet: str = Field(min_length=1)
    chunk_id: int | None = Field(default=None, gt=0)


class MeetingBrief(BriefModel):
    """The complete executive brief for one meeting."""

    meeting_title: str = Field(min_length=1)
    time_window: str | None = None
    last_meeting_recap: str = ""
    open_action_items: list[ActionItem] = Field(default_factory=list)
    key_topics_today: list[str] = Field(default_factory=list)
    proposed_agenda: list[AgendaItem] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)

    @field_validator("time_window")
    @classmethod
    def _check_window(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        value = value.strip()
        if not _TIME_WINDOW.match(value):
            raise ValueError(
                f"time_window must be 'YYYY-MM-DD..YYYY-MM-DD', got {value!r}"
            )
        return value

    @field_validator("key_topics_today")
    @classmethod
    def _drop_blank_topics(cls, value: list[str]) -> list[str]:
        return [t.strip() for t in value if t and t.strip()]

    @field_validator(
        "open_action_items",
        "key_topics_today",
        "proposed_agenda",
        "evidence",
        mode="before",
    )
    @classmethod
    def _none_is_empty(cls, value: Any) -> Any:
        """A missing list arrives as `null` often enough to be worth absorbing."""
        return [] if value is None else value

    @property
    def total_agenda_minutes(self) -> int:
        return sum(item.minutes for item in self.proposed_agenda)


class BriefRecord(Record):
    """A row of the `briefs` table.

    `brief` stays a raw dict rather than a `MeetingBrief`. Briefs are written
    once and read for years; parsing an old row through today's validators
    would mean a schema tightening retroactively breaks history. Callers that
    want the typed object ask for it with `as_brief()` and handle the failure.
    """

    id: str
    meeting_id: str
    created_at: str
    model: str | None = None
    brief: dict[str, Any]

    def as_brief(self) -> MeetingBrief:
        """Validate the stored payload against the current schema."""
        return MeetingBrief.model_validate(self.brief)


class BriefSummary(Record):
    """A `briefs` row without the payload, for the history dropdown."""

    id: str
    meeting_id: str
    created_at: str
    model: str | None = None
