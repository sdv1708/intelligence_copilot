
"""Pydantic models for MeetingBrief and related structures."""

from pydantic import BaseModel
from typing import Optional, List, Literal


class ActionItem(BaseModel):
    """Represents a single action item from the meeting."""
    owner: str
    item: str
    due: Optional[str] = None  # YYYY-MM-DD format
    status: Literal["open", "blocked", "done"] = "open"


class AgendaItem(BaseModel):
    """Represents a single agenda item for the meeting."""
    topic: str
    minutes: int
    owner: Optional[str] = None


class Evidence(BaseModel):
    """Reference to source material for a point in the brief."""
    source: str  # Format: "material_id#c{chunk_idx}"
    snippet: str


class MeetingBrief(BaseModel):
    """Complete meeting brief with all sections."""
    meeting_title: str
    time_window: Optional[str] = None  # Format: "2025-11-01..2025-11-07"
    last_meeting_recap: str
    open_action_items: List[ActionItem]
    key_topics_today: List[str]
    proposed_agenda: List[AgendaItem]
    evidence: List[Evidence]

