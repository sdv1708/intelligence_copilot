"""Recall and retrieval logic for fetching relevant context."""

import sqlite3
from typing import Any

from core.document_handler import format_context_with_relationships, recall_with_context


def recall_context(db_conn: sqlite3.Connection, meeting_id: str, 
                   query: str = "", k: int = 8) -> list[dict[str, Any]]:
    """
    Retrieve top-k relevant context for a meeting.
    Uses improved recall with surrounding chunks to preserve relationships.
    
    Args:
        db_conn: SQLite database connection
        meeting_id: ID of the meeting
        query: Optional search query (if empty, use all material from meeting)
        k: Number of results to return
    
    Returns:
        List of dicts with keys: {text, material_id, chunk_idx, score}
    """
    # Use improved recall with context preservation
    return recall_with_context(db_conn, meeting_id, query=query, k=k, include_surrounding=True)


def format_context_blocks(results: list[dict[str, Any]]) -> str:
    """
    Format retrieved chunks into context blocks for the LLM prompt.
    Uses improved formatting that preserves relationships.
    
    Args:
        results: List of retrieved chunks from recall_context
    
    Returns:
        Formatted string for inclusion in prompt
    """
    return format_context_with_relationships(results)
