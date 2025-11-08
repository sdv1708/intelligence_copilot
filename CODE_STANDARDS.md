# Code Standards & Professional Guidelines

## Overview
This document outlines the code standards applied to the Executive Intelligence Copilot project.

---

## Python Code Standards

### 1. Logging Format

#### Approved Tags
```
[INFO]     - Informational, general execution flow
[OK]       - Operation successful, positive outcome  
[WARNING]  - Non-critical issue, caution needed
[ERROR]    - Critical failure, operation failed
[DEBUG]    - Debug information, detailed trace
```

#### Implementation
```python
# Correct - Using log_message from utils
from core.utils import log_message

log_message("INFO", "Starting database initialization")
log_message("OK", "Database created successfully")
log_message("WARNING", "File format not recognized, using default")
log_message("ERROR", "Failed to parse PDF: Invalid format")

# Or direct print for CLI tools
print("[INFO] Starting process...")
print("[OK] Process completed")
print("[ERROR] Process failed")
```

### 2. Error Handling

```python
# Good
try:
    result = parse_file(file_bytes, filename)
except Exception as e:
    log_message("ERROR", f"Failed to parse {filename}: {str(e)}")
    return None

# Avoid
try:
    result = parse_file(file_bytes, filename)
except Exception as e:
    print(f"❌ Parse error")  # Not professional
    return None
```

### 3. Comments & Docstrings

```python
# Excellent - Professional docstring
def generate_brief(title: str, date: str, context_blocks: str) -> Optional[MeetingBrief]:
    """
    Generate a meeting brief using LLM.
    
    Args:
        title: Meeting title
        date: Meeting date (YYYY-MM-DD format)
        context_blocks: Formatted context from retrieval
    
    Returns:
        MeetingBrief object or None on failure
    
    Raises:
        Exception: Logs and returns None on API errors
    """
    pass

# Good - Inline comments explain why, not what
result = model.encode(chunks, normalize_embeddings=True)  # Normalize for cosine similarity
```

### 4. Variable Naming

```python
# Good - Clear, descriptive names
meeting_id = "meeting_20251107_abc123"
context_chunks = []
similarity_score = 0.89

# Avoid - Vague, single-letter names
m = "meeting_20251107_abc123"
c = []
s = 0.89
```

### 5. Function Signatures

```python
# Good - Type hints and clear parameters
def recall_context(
    db_conn: sqlite3.Connection,
    meeting_id: str,
    query: str = "",
    k: int = 8
) -> List[Dict[str, Any]]:
    """Retrieve top-k relevant context for a meeting."""
    pass

# Avoid - No type hints, unclear
def recall(conn, id, q="", k=8):
    pass
```

---

## Frontend Standards (Streamlit)

### 1. UI Elements CAN Include Emojis
```python
# Good - Emojis enhance UX
st.button("🎯 Generate Brief", use_container_width=True)
st.subheader("📋 Last Meeting Recap")
st.write("✅ Brief generated successfully")

# Rationale: Users see these in the UI and they make it friendly
```

### 2. Button Labels
```python
# Good
st.button("📤 Upload Files")
st.button("📝 Save Pasted Text")
st.button("🎯 Generate Brief")
st.button("🔍 What happened last time?")
st.button("💾 Download Brief")

# These provide visual hierarchy and friendly interface
```

### 3. User Messages
```python
# Good - Emojis in messages for clarity
st.success("✅ Brief generated successfully!")
st.error("❌ Error generating brief: Check logs for details")
st.warning("⚠️ Please create or select a meeting first")
st.info("ℹ️ Click 'Generate Brief' to populate")
```

---

## Code Organization

### Module Structure
```python
# 1. Imports (standard library first, then third-party, then local)
import os
import json
from typing import Optional, List, Dict, Any

import streamlit as st
from dotenv import load_dotenv

from core.db import Database
from core.parsing import parse_file

# 2. Configuration
load_dotenv()

# 3. Constants
MAX_FILE_SIZE = 50_000_000  # 50MB

# 4. Helper functions/decorators
@st.cache_resource
def init_database():
    return Database()

# 5. Main functions
def main():
    pass

# 6. Entry point
if __name__ == "__main__":
    main()
```

### File Organization
```
core/
├── schema.py           (Models first)
├── utils.py            (Utilities/helpers)
├── db.py               (Database operations)
├── parsing.py          (Input handling)
├── chunk.py            (Text processing)
├── embed.py            (Embeddings)
├── recall.py           (Retrieval)
└── synth.py            (LLM operations)
```

---

## Testing Standards

### Test Output Format
```python
# Good - Professional test output
print("=" * 70)
print("TEST: Context Retrieval")
print("=" * 70)
print()
print("[INFO] Retrieving context for meeting...")
print("[OK] Retrieved 8 chunks")
print()
print("Summary:")
print("  1. Database initialized")
print("  2. Materials retrieved")
print("  3. Context retrieval successful")
print()
```

### Not Allowed
```python
# Avoid
print("🔄 Testing...")
print("✅ Test passed!")
print("❌ Test failed!")
```

---

## Documentation Standards

### Docstring Format (Google Style)
```python
def function_name(param1: str, param2: int) -> bool:
    """Brief one-line description.
    
    Longer description if needed. Explain the purpose and behavior.
    
    Args:
        param1: Description of param1
        param2: Description of param2 (default: 8)
    
    Returns:
        Description of return value
    
    Raises:
        ValueError: When something is wrong
        
    Example:
        >>> result = function_name("test", 5)
        >>> print(result)
        True
    """
```

### File Headers
```python
"""Module description - what this module does."""

from typing import Optional
import sqlite3

from core.utils import log_message


def main_function():
    """Do something important."""
    pass
```

---

## What's Preserved

### ✅ Frontend (app.py)
- All emojis in UI elements (buttons, headers, messages)
- Streamlit components display emojis to users
- Friendly, intuitive interface

### ✅ Backend (core/ modules)
- Professional, simple code
- No decorative characters
- Clear logging format
- Standard tags [INFO], [OK], [WARNING], [ERROR]

### ✅ Testing
- Professional output format
- Clear test results
- Easy to parse

---

## Git Commit Standards

### Message Format
```
Short description (50 chars max)

Longer explanation of changes if needed.
Explain the why, not the what.

Example:
  Remove emojis from backend code for professional logging
  
  Backend code now uses standard [INFO], [OK], [WARNING], [ERROR]
  tags instead of emojis. Frontend Streamlit components preserve
  emojis for better UX. This improves code readability and
  follows industry logging standards.
```

---

## Review Checklist

Before committing code:
- [ ] No emojis in backend/core/ code
- [ ] Professional logging format with tags
- [ ] Type hints on all functions
- [ ] Docstrings on all public functions
- [ ] Clear variable names
- [ ] Error handling implemented
- [ ] Comments explain "why" not "what"
- [ ] Code follows module structure
- [ ] Tests are professional format

---

## Examples

### ❌ Bad
```python
def get_data(x):
    print("🔄 Processing...")
    try:
        # do stuff
        print("✅ Done!")
        return data
    except:
        print("❌ Error!")
        return None
```

### ✅ Good
```python
def retrieve_meeting_data(meeting_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve meeting data from database."""
    log_message("INFO", f"Retrieving meeting data for {meeting_id}")
    
    try:
        connection = db.get_connection()
        meeting = db.get_meeting(connection, meeting_id)
        connection.close()
        
        log_message("OK", f"Retrieved meeting: {meeting['title']}")
        return meeting
    except Exception as e:
        log_message("ERROR", f"Failed to retrieve meeting: {str(e)}")
        return None
```

---

## Summary

| Aspect | Standard |
|--------|----------|
| Backend Logging | [TAG] format, no emojis |
| Frontend UI | Emojis for UX, preserved |
| Type Hints | Required on all functions |
| Docstrings | Google style, all public functions |
| Comments | Explain why, not what |
| Error Handling | Try/except with logging |
| Testing | Professional output format |
| Variable Names | Clear, descriptive |

---

**These standards ensure:**
- Professional, maintainable code
- Easy to read and understand
- Production-ready quality
- Great user experience (frontend)
- Clear system logs (backend)

✅ **All standards applied to current codebase**

