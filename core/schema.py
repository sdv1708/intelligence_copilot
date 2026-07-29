
"""Pydantic models for MeetingBrief and related structures."""

from typing import Literal

from pydantic import BaseModel


class ActionItem(BaseModel):
    """Represents a single action item from the meeting."""
    owner: str
    item: str
    due: str | None = None  # YYYY-MM-DD format
    status: Literal["open", "blocked", "done"] = "open"


class AgendaItem(BaseModel):
    """Represents a single agenda item for the meeting."""
    topic: str
    minutes: int
    owner: str | None = None


class Evidence(BaseModel):
    """Reference to source material for a point in the brief."""
    source: str  # Format: "material_id#c{chunk_idx}"
    snippet: str


class MeetingBrief(BaseModel):
    """Complete meeting brief with all sections."""
    meeting_title: str
    time_window: str | None = None  # Format: "2025-11-01..2025-11-07"
    last_meeting_recap: str
    open_action_items: list[ActionItem]
    key_topics_today: list[str]
    proposed_agenda: list[AgendaItem]
    evidence: list[Evidence]

