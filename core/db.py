"""Database initialization and CRUD operations using SQLite."""

import sqlite3
import json
from typing import Optional, List, Dict, Any
from datetime import datetime
from core.utils import get_env, generate_id, log_message


class Database:
    """SQLite database manager for meetings, materials, and briefs."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or get_env("DB_PATH", "./data/briefs.db")
        self.init_db()

    def get_connection(self):
        """Get a database connection."""
        return sqlite3.connect(self.db_path)

    def init_db(self):
        """Initialize database schema."""
        conn = self.get_connection()
        cursor = conn.cursor()

        # Meetings table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS meetings (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                date TEXT,
                attendees TEXT,
                tags TEXT,
                created_at TEXT NOT NULL
            )
        """)

        # Materials table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS materials (
                id TEXT PRIMARY KEY,
                meeting_id TEXT NOT NULL,
                filename TEXT,
                media_type TEXT,
                text TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (meeting_id) REFERENCES meetings(id)
            )
        """)

        # Briefs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS briefs (
                id TEXT PRIMARY KEY,
                meeting_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                model TEXT,
                brief_json TEXT NOT NULL,
                FOREIGN KEY (meeting_id) REFERENCES meetings(id)
            )
        """)

        conn.commit()
        conn.close()
        log_message("INFO", f"Database initialized at {self.db_path}")

    def create_meeting(self, title: str, date: Optional[str] = None, 
                      attendees: Optional[str] = None, tags: Optional[str] = None) -> str:
        """Create a new meeting. Returns meeting_id."""
        meeting_id = generate_id("meeting")
        created_at = datetime.now().isoformat()
        
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO meetings (id, title, date, attendees, tags, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (meeting_id, title, date, attendees, tags, created_at))
        conn.commit()
        conn.close()
        log_message("INFO", f"Created meeting: {meeting_id} - {title}")
        return meeting_id

    def get_meeting(self, meeting_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a meeting by ID."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM meetings WHERE id = ?", (meeting_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {
                "id": row[0],
                "title": row[1],
                "date": row[2],
                "attendees": row[3],
                "tags": row[4],
                "created_at": row[5]
            }
        return None

    def list_meetings(self) -> List[Dict[str, Any]]:
        """List all meetings."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM meetings ORDER BY created_at DESC")
        rows = cursor.fetchall()
        conn.close()
        
        return [
            {
                "id": row[0],
                "title": row[1],
                "date": row[2],
                "attendees": row[3],
                "tags": row[4],
                "created_at": row[5]
            }
            for row in rows
        ]

    def add_material(self, meeting_id: str, filename: str, media_type: str, text: str) -> str:
        """Add a material to a meeting. Returns material_id."""
        material_id = generate_id("material")
        created_at = datetime.now().isoformat()
        
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO materials (id, meeting_id, filename, media_type, text, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (material_id, meeting_id, filename, media_type, text, created_at))
        conn.commit()
        conn.close()
        log_message("INFO", f"Added material: {material_id} to meeting {meeting_id}")
        return material_id

    def get_materials(self, meeting_id: str) -> List[Dict[str, Any]]:
        """Get all materials for a meeting."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, filename, media_type, LENGTH(text), created_at FROM materials
            WHERE meeting_id = ? ORDER BY created_at DESC
        """, (meeting_id,))
        rows = cursor.fetchall()
        conn.close()
        
        return [
            {
                "id": row[0],
                "filename": row[1],
                "media_type": row[2],
                "char_count": row[3],
                "created_at": row[4]
            }
            for row in rows
        ]

    def save_brief(self, meeting_id: str, model: str, brief_dict: Dict[str, Any]) -> str:
        """Save a generated brief. Returns brief_id."""
        brief_id = generate_id("brief")
        created_at = datetime.now().isoformat()
        brief_json = json.dumps(brief_dict)
        
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO briefs (id, meeting_id, created_at, model, brief_json)
            VALUES (?, ?, ?, ?, ?)
        """, (brief_id, meeting_id, created_at, model, brief_json))
        conn.commit()
        conn.close()
        log_message("INFO", f"Saved brief: {brief_id} for meeting {meeting_id}")
        return brief_id

    def get_latest_brief(self, meeting_id: str) -> Optional[Dict[str, Any]]:
        """Get the latest brief for a meeting."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, created_at, model, brief_json FROM briefs
            WHERE meeting_id = ? ORDER BY created_at DESC LIMIT 1
        """, (meeting_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {
                "id": row[0],
                "created_at": row[1],
                "model": row[2],
                "brief": json.loads(row[3])
            }
        return None

    def get_brief_history(self, meeting_id: str) -> List[Dict[str, Any]]:
        """Get all briefs for a meeting (history)."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, created_at, model FROM briefs
            WHERE meeting_id = ? ORDER BY created_at DESC
        """, (meeting_id,))
        rows = cursor.fetchall()
        conn.close()
        
        return [
            {
                "id": row[0],
                "created_at": row[1],
                "model": row[2]
            }
            for row in rows
        ]

    def get_brief_by_id(self, brief_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a specific brief by ID."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, meeting_id, created_at, model, brief_json FROM briefs WHERE id = ?
        """, (brief_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {
                "id": row[0],
                "meeting_id": row[1],
                "created_at": row[2],
                "model": row[3],
                "brief": json.loads(row[4])
            }
        return None

