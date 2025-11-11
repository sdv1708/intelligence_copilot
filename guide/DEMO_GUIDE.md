# Executive Intelligence Copilot - Demo Guide

**Purpose:** Complete system flow documentation mapping UI components to backend operations for perfect demo execution.

---

## 📋 Table of Contents

1. [System Overview](#system-overview)
2. [UI Components → Backend Mapping](#ui-components--backend-mapping)
3. [Complete User Flow](#complete-user-flow)
4. [Demo Script (Step-by-Step)](#demo-script-step-by-step)
5. [Technical Flow Diagrams](#technical-flow-diagrams)
6. [Troubleshooting Tips](#troubleshooting-tips)

---

## 🎯 System Overview

The Executive Intelligence Copilot is a **4-agent AI system** that transforms meeting materials into executive-ready briefs:

```
UI Action → Backend Agent → Processing → Storage → Display
```

**Key Components:**
- **Frontend:** Streamlit UI (`app.py`)
- **Orchestrator:** Multi-agent coordinator (`agents/copilot_orchestrator.py`)
- **Core Modules:** Database, parsing, embeddings, recall, synthesis
- **Storage:** SQLite (structured data) + FAISS (vector embeddings)

---

## 🖥️ UI Components → Backend Mapping

### Sidebar Components

#### 1. **Meeting Selection Section**

**UI Component:** Radio button + Form inputs
- **Location:** `app.py:484-558`
- **Options:** "Create New Meeting" or "Select Existing Meeting"

**Backend Flow:**

**Create New Meeting:**
```
User Input (Title, Date, Attendees, Tags)
    ↓
app.py:497 → st.button("✅ Create Meeting")
    ↓
core/db.py:create_meeting()
    ├─ Generate meeting_id (UUID)
    ├─ INSERT INTO meetings table
    └─ Return meeting_id
    ↓
st.session_state.current_meeting_id = meeting_id
    ↓
UI: Success message + Rerun
```

**Select Existing Meeting:**
```
User selects from dropdown
    ↓
app.py:527 → st.selectbox()
    ↓
core/db.py:list_meetings()
    ├─ SELECT * FROM meetings ORDER BY created_at DESC
    └─ Return list of meetings
    ↓
st.session_state.current_meeting_id = selected_id
    ↓
UI: Display selected meeting info
```

---

#### 2. **Materials Section**

**UI Component:** File uploader OR Text area
- **Location:** `app.py:562-648`
- **Options:** "Upload Files" or "Paste Text"

**Backend Flow:**

**Upload Files:**
```
User selects files (PDF/DOCX/PPTX/TXT)
    ↓
app.py:582 → st.button("📤 Upload Files")
    ↓
For each file:
    ├─ app.py:597 → parse_file(file_bytes, filename)
    │   └─ core/parsing.py:parse_file()
    │       ├─ Detect format (PDF/DOCX/PPTX/TXT)
    │       ├─ Extract text content
    │       └─ Return (text, media_type)
    │
    ├─ app.py:600 → db.add_material()
    │   └─ core/db.py:add_material()
    │       ├─ Generate material_id
    │       ├─ INSERT INTO materials table
    │       └─ Return material_id
    │
    └─ app.py:596 → orchestrator.ingest_material()
        └─ agents/copilot_orchestrator.py:ingest_material()
            ├─ Parse file (already done)
            ├─ core/chunk.py:chunk_text() → chunks
            ├─ core/embed.py:encode() → embeddings (384-dim)
            ├─ core/embed.py:build_or_load_index() → FAISS index
            ├─ core/embed.py:add_to_index() → Store embeddings
            └─ Return success
    ↓
UI: Success message + Progress bar + Balloons
```

**Paste Text:**
```
User pastes text in textarea
    ↓
app.py:631 → st.button("📝 Save Text")
    ↓
app.py:633 → parse_pasted_text(pasted_text)
    └─ core/parsing.py:parse_pasted_text()
        └─ Return (text, "pasted")
    ↓
app.py:636 → db.add_material()
    └─ Same flow as Upload Files
    ↓
UI: Success message + Character count
```

---

#### 3. **Actions Section**

**UI Component:** Action buttons
- **Location:** `app.py:652-780`

**A. Generate Brief Button**

```
User clicks "🎯 Generate Brief"
    ↓
app.py:664 → st.button("🎯 Generate Brief")
    ↓
app.py:668 → orchestrator.generate_brief()
    └─ agents/copilot_orchestrator.py:generate_brief()
        │
        ├─ STEP 0: Cross-Meeting Memory (Optional)
        │   └─ _get_previous_meeting_context()
        │       ├─ Query meetings with same title
        │       ├─ Get most recent brief
        │       └─ Format previous context
        │
        ├─ STEP 1: Recall Agent
        │   └─ recall_context_tool()
        │       └─ core/recall.py:recall_context()
        │           ├─ Fetch materials from DB
        │           ├─ Chunk all materials
        │           ├─ Generate query embedding
        │           ├─ Search FAISS (top-8 chunks)
        │           └─ Format context blocks
        │
        ├─ STEP 2: Synthesis Agent
        │   ├─ Load prompts (system_prompt.txt, user_prompt.txt)
        │   ├─ Build final prompt with context
        │   ├─ Prepend previous meeting context (if available)
        │   ├─ Create LangChain messages
        │   ├─ Call LLM (Gemini/GPT-4/Claude)
        │   ├─ Extract JSON from response
        │   ├─ Repair incomplete JSON
        │   ├─ Validate fields, add defaults
        │   └─ Create MeetingBrief object
        │
        └─ STEP 3: Memory Agent
            └─ db.save_brief()
                ├─ Serialize MeetingBrief → JSON
                ├─ INSERT INTO briefs table
                └─ Return brief_id
    ↓
st.session_state.generated_brief = brief
st.session_state.brief_meeting_id = meeting_id
    ↓
UI: Display brief in 5 sections (Recap, Items, Topics, Agenda, Evidence)
```

**B. Recall Previous Button**

```
User clicks "🔍 Recall Previous"
    ↓
app.py:699 → st.button("🔍 Recall Previous")
    ↓
app.py:701 → orchestrator.recall_previous_brief()
    └─ agents/copilot_orchestrator.py:recall_previous_brief()
        └─ core/db.py:get_latest_brief()
            ├─ SELECT * FROM briefs WHERE meeting_id = ?
            ├─ ORDER BY created_at DESC LIMIT 1
            ├─ Deserialize JSON → MeetingBrief
            └─ Return MeetingBrief object
    ↓
st.session_state.generated_brief = brief
    ↓
UI: Display previous brief
```

**C. Download Button**

```
User clicks "💾 Download"
    ↓
app.py:719 → st.button("💾 Download")
    ↓
app.py:721 → Toggle download options
    ↓
User selects format (JSON/Markdown)
    ↓
app.py:728 → convert_brief_to_markdown() OR json.dumps()
    └─ app.py:196 → convert_brief_to_markdown()
        └─ Format MeetingBrief → Markdown string
    ↓
app.py:732 → st.download_button()
    └─ Trigger file download
```

**D. Brief History**

```
User selects brief from dropdown
    ↓
app.py:780 → st.button("📖 Load")
    ↓
app.py:782 → db.get_brief_by_id()
    └─ core/db.py:get_brief_by_id()
        ├─ SELECT * FROM briefs WHERE id = ?
        ├─ Deserialize JSON → MeetingBrief
        └─ Return MeetingBrief object
    ↓
st.session_state.generated_brief = brief
    ↓
UI: Display selected brief
```

---

### Main Content Area

#### 4. **Materials Table**

**UI Component:** Dataframe display
- **Location:** `app.py:848-920`

```
Page Load / After Upload
    ↓
app.py:848 → Display materials section
    ↓
app.py:851 → db.get_materials()
    └─ core/db.py:get_materials()
        ├─ SELECT * FROM materials WHERE meeting_id = ?
        └─ Return list of materials
    ↓
app.py:857 → st.dataframe() → Display table
    ├─ Columns: Filename, Type, Size, Added
    └─ Delete button for each row
```

**Delete Material:**
```
User clicks "🗑️ Delete"
    ↓
app.py:894 → st.button("🗑️ Delete")
    ↓
app.py:896 → db.delete_material()
    └─ core/db.py:delete_material()
        └─ DELETE FROM materials WHERE id = ?
    ↓
UI: Rerun → Updated table
```

---

#### 5. **Brief Display**

**UI Component:** Tabs with sections
- **Location:** `app.py:826-842` + `render_brief()`

```
Brief exists in session_state
    ↓
app.py:827 → Check if brief matches current meeting
    ↓
app.py:832 → render_brief(brief)
    └─ app.py:341 → render_brief()
        ├─ Tab 1: Last Meeting Recap
        ├─ Tab 2: Open Action Items (with status badges)
        ├─ Tab 3: Key Topics Today
        ├─ Tab 4: Proposed Agenda (with time estimates)
        └─ Tab 5: Evidence (with source citations)
    ↓
UI: Display formatted brief sections
```

---

#### 6. **Q&A Section**

**UI Component:** Text input + Conversation history
- **Location:** `app.py:247-339` + `render_qa_section()`

```
User enters question
    ↓
app.py:279 → st.button("🔍 Ask")
    ↓
app.py:289 → orchestrator.answer_question()
    └─ agents/copilot_orchestrator.py:answer_question()
        ├─ STEP 1: Recall context for question
        │   └─ core/recall.py:recall_context(query=question, k=5)
        │       ├─ Generate query embedding
        │       ├─ Search FAISS (top-5 chunks)
        │       └─ Format context blocks
        │
        ├─ STEP 2: Load QA prompts
        │   ├─ prompts/qa_system_prompt.txt
        │   └─ prompts/qa_user_prompt.txt
        │
        ├─ STEP 3: Build prompt with question
        │   └─ Replace {{question}} and {{context_blocks}}
        │
        ├─ STEP 4: Call LLM
        │   └─ LLM.invoke(messages) → Answer
        │
        └─ STEP 5: Extract sources
            └─ _extract_sources_from_context()
    ↓
st.session_state.qa_history.append({
    "question": question,
    "answer": answer,
    "sources": sources,
    "timestamp": timestamp
})
    ↓
UI: Display question + answer + sources in conversation format
```

---

## 🔄 Complete User Flow

### Flow 1: Create Meeting → Upload Materials → Generate Brief

```
1. USER ACTION: Create New Meeting
   UI: Sidebar → "Create New Meeting" → Fill form → Click "✅ Create Meeting"
   BACKEND: db.create_meeting() → INSERT INTO meetings
   RESULT: Meeting created, meeting_id stored in session_state

2. USER ACTION: Upload Files
   UI: Sidebar → "Upload Files" → Select files → Click "📤 Upload Files"
   BACKEND: 
     - parse_file() → Extract text
     - db.add_material() → Save to DB
     - orchestrator.ingest_material() → Chunk → Embed → Index FAISS
   RESULT: Materials stored, embeddings indexed

3. USER ACTION: Generate Brief
   UI: Sidebar → Click "🎯 Generate Brief"
   BACKEND:
     - Step 0: Check previous meetings (cross-meeting memory)
     - Step 1: Recall Agent → Vector search (top-8 chunks)
     - Step 2: Synthesis Agent → LLM call → JSON parsing
     - Step 3: Memory Agent → Save to DB
   RESULT: Brief displayed in main area (5 tabs)

4. USER ACTION: View Brief
   UI: Main area → Brief tabs (Recap, Items, Topics, Agenda, Evidence)
   BACKEND: render_brief() → Format MeetingBrief object
   RESULT: Formatted brief display

5. USER ACTION: Download Brief
   UI: Sidebar → Click "💾 Download" → Select format → Download
   BACKEND: convert_brief_to_markdown() OR json.dumps()
   RESULT: File download (JSON or Markdown)
```

### Flow 2: Select Existing Meeting → Generate Brief → Recall Previous

```
1. USER ACTION: Select Existing Meeting
   UI: Sidebar → "Select Existing Meeting" → Choose from dropdown
   BACKEND: db.list_meetings() → SELECT * FROM meetings
   RESULT: Meeting selected, materials loaded

2. USER ACTION: Generate Brief
   UI: Sidebar → Click "🎯 Generate Brief"
   BACKEND: Same as Flow 1, Step 3
   RESULT: New brief generated

3. USER ACTION: Recall Previous Brief
   UI: Sidebar → Click "🔍 Recall Previous"
   BACKEND: db.get_latest_brief() → Get most recent brief
   RESULT: Previous brief displayed

4. USER ACTION: Load Historical Brief
   UI: Sidebar → Brief History dropdown → Select → Click "📖 Load"
   BACKEND: db.get_brief_by_id() → Get specific brief
   RESULT: Selected brief displayed
```

### Flow 3: Q&A Feature

```
1. USER ACTION: Ask Question
   UI: Main area → Q&A section → Enter question → Click "🔍 Ask"
   BACKEND:
     - recall_context(query=question, k=5) → Semantic search
     - Load QA prompts
     - Call LLM → Generate answer
     - Extract sources
   RESULT: Answer displayed with sources

2. USER ACTION: Continue Conversation
   UI: Ask another question
   BACKEND: Same as above (each question is independent)
   RESULT: Conversation history grows
```

---

## 🎬 Demo Script (Step-by-Step)

### **Recommended Demo Order (5-7 minutes)**

#### **Phase 1: Setup & Introduction (30 seconds)**

**What to Say:**
> "I'm going to show you how the Executive Intelligence Copilot transforms hours of meeting prep into minutes. This is a 4-agent AI system that analyzes documents and generates executive-ready briefs."

**Actions:**
1. Open the application
2. Point out the UI layout (Sidebar + Main area)
3. Show GPU/CPU status badge (if GPU available, highlight speed)

**What Happens:**
- App loads
- Embedding model preloads (shows device)
- Database initializes

---

#### **Phase 2: Create Meeting (30 seconds)**

**What to Say:**
> "First, let's create a meeting. The system stores everything in SQLite, so each meeting is isolated."

**Actions:**
1. Sidebar → Select "Create New Meeting"
2. Enter:
   - Title: "Q4 Strategy Review"
   - Date: Today's date
   - Attendees: "John, Jane, Bob"
   - Tags: "strategy, planning"
3. Click "✅ Create Meeting"

**What Happens:**
- `db.create_meeting()` → INSERT INTO meetings
- Session state updates
- Success message appears

**Backend Flow:**
```
UI Input → core/db.py:create_meeting() → SQLite INSERT → Success
```

---

#### **Phase 3: Upload Materials (1 minute)**

**What to Say:**
> "Now let's add materials. The Ingestion Agent will parse files, chunk them, generate embeddings using a neural network, and index them in FAISS for semantic search."

**Actions:**
1. Sidebar → "Upload Files"
2. Select 2-3 files (PDF, DOCX, or TXT)
3. Click "📤 Upload Files"
4. Watch progress bar

**What Happens:**
- Files parse (extract text)
- Materials saved to database
- **Ingestion Agent activates:**
  - Chunks text (1200 chars, 120 overlap)
  - Generates embeddings (384-dim vectors)
  - Indexes in FAISS
- Success message + balloons

**Backend Flow:**
```
File Upload → core/parsing.py:parse_file()
    ↓
core/db.py:add_material() → SQLite INSERT
    ↓
agents/copilot_orchestrator.py:ingest_material()
    ├─ core/chunk.py:chunk_text() → Chunks
    ├─ core/embed.py:encode() → Embeddings (ML model)
    └─ core/embed.py:add_to_index() → FAISS index
```

**Demo Tip:** If GPU available, mention "Notice how fast the embeddings generate - that's GPU acceleration."

---

#### **Phase 4: Generate Brief (2 minutes)**

**What to Say:**
> "Now the magic happens. When I click Generate Brief, four AI agents work together: Recall Agent finds relevant context using semantic search, Synthesis Agent uses a large language model to create the brief, and Memory Agent saves it. The system also checks for previous meetings with the same title to provide continuity."

**Actions:**
1. Sidebar → Click "🎯 Generate Brief"
2. Show spinner: "🤖 Generating brief with AI agents..."
3. Wait for completion (5-15 seconds)

**What Happens:**
- **Step 0:** Cross-meeting memory check (if previous meetings exist)
- **Step 1:** Recall Agent → Vector search (top-8 chunks)
- **Step 2:** Synthesis Agent → LLM call → JSON parsing
- **Step 3:** Memory Agent → Save to database
- Brief appears in main area

**Backend Flow:**
```
Button Click → agents/copilot_orchestrator.py:generate_brief()
    ├─ Step 0: _get_previous_meeting_context() (optional)
    ├─ Step 1: recall_context_tool() → FAISS search
    ├─ Step 2: LLM call → JSON parsing → Validation
    └─ Step 3: db.save_brief() → SQLite INSERT
```

**Demo Tip:** 
- Point out the 5 tabs: Recap, Action Items, Topics, Agenda, Evidence
- Show evidence citations (source references)
- Highlight action items with status badges

---

#### **Phase 5: Explore Brief Sections (1 minute)**

**What to Say:**
> "The brief has five sections. Notice how each point has evidence citations showing where the information came from."

**Actions:**
1. Click through tabs:
   - **Recap:** Show meeting summary
   - **Action Items:** Show owner, item, status
   - **Key Topics:** Show bullet points
   - **Agenda:** Show time estimates
   - **Evidence:** Show source citations

**What Happens:**
- `render_brief()` formats each section
- Evidence shows material_id#chunk_idx references

---

#### **Phase 6: Download & History (30 seconds)**

**What to Say:**
> "You can download the brief in JSON or Markdown format, and the system maintains a history of all generated briefs."

**Actions:**
1. Sidebar → Click "💾 Download"
2. Select format (JSON or Markdown)
3. Download file
4. Show Brief History dropdown (if multiple briefs exist)

**What Happens:**
- `convert_brief_to_markdown()` formats output
- `st.download_button()` triggers download
- History shows all briefs for the meeting

---

#### **Phase 7: Recall Previous Brief (30 seconds)**

**What to Say:**
> "The Memory Agent enables 'What happened last time?' - perfect for recurring meetings."

**Actions:**
1. Sidebar → Click "🔍 Recall Previous"
2. Show previous brief loads

**What Happens:**
- `db.get_latest_brief()` queries database
- Deserializes JSON → MeetingBrief
- Displays previous brief

---

#### **Phase 8: Q&A Feature (1 minute)**

**What to Say:**
> "Finally, the Q&A feature lets you ask questions about your materials. It uses semantic search to find relevant context and generates answers with source citations."

**Actions:**
1. Scroll to Q&A section
2. Enter question: "What are the key risks mentioned?"
3. Click "🔍 Ask"
4. Show answer with sources
5. Ask follow-up question

**What Happens:**
- `recall_context(query=question, k=5)` → Semantic search
- Load QA prompts
- Call LLM → Generate answer
- Extract sources
- Display in conversation format

**Backend Flow:**
```
Question Input → agents/copilot_orchestrator.py:answer_question()
    ├─ core/recall.py:recall_context(query, k=5) → FAISS search
    ├─ Load QA prompts
    ├─ Call LLM → Answer
    └─ Extract sources
```

**Demo Tip:** Show how sources are cited (material_id#chunk_idx)

---

#### **Phase 9: Cross-Meeting Memory (30 seconds) - Optional**

**What to Say:**
> "If you create another meeting with the same title, the system automatically includes context from the previous meeting."

**Actions:**
1. Create new meeting with same title
2. Upload materials
3. Generate brief
4. Point out previous meeting context in the brief

**What Happens:**
- `_get_previous_meeting_context()` finds previous meeting
- Formats previous brief context
- Prepends to prompt

---

### **Quick Demo (2 minutes) - If Time is Limited**

1. **Create Meeting** (15s)
2. **Upload 1 File** (15s)
3. **Generate Brief** (30s)
4. **Show Brief Sections** (30s)
5. **Q&A Example** (30s)

---

## 🔧 Technical Flow Diagrams

### Complete End-to-End Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    USER INTERFACE (app.py)                  │
└─────────────────────────────────────────────────────────────┘
                            │
                            │ User Actions
                            ▼
┌─────────────────────────────────────────────────────────────┐
│              SESSION STATE MANAGEMENT                        │
│  - current_meeting_id                                       │
│  - generated_brief                                          │
│  - qa_history                                              │
└─────────────────────────────────────────────────────────────┘
                            │
                            │ Function Calls
                            ▼
┌─────────────────────────────────────────────────────────────┐
│         ORCHESTRATOR (agents/copilot_orchestrator.py)       │
│                                                              │
│  ┌────────────────────────────────────────────────────┐    │
│  │  INGESTION AGENT                                   │    │
│  │  ingest_material()                                 │    │
│  │    ├─ parse_file() → core/parsing.py              │    │
│  │    ├─ chunk_text() → core/chunk.py                │    │
│  │    ├─ encode() → core/embed.py (ML model)         │    │
│  │    └─ add_to_index() → FAISS                      │    │
│  └────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌────────────────────────────────────────────────────┐    │
│  │  RECALL AGENT                                      │    │
│  │  recall_context_tool()                             │    │
│  │    └─ recall_context() → core/recall.py           │    │
│  │        ├─ Query FAISS                             │    │
│  │        └─ Format context blocks                   │    │
│  └────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌────────────────────────────────────────────────────┐    │
│  │  SYNTHESIS AGENT                                   │    │
│  │  generate_brief()                                  │    │
│  │    ├─ _get_previous_meeting_context()            │    │
│  │    ├─ Load prompts                                 │    │
│  │    ├─ Call LLM → core/llm_providers.py            │    │
│  │    ├─ Parse JSON                                   │    │
│  │    └─ Validate → core/schema.py                    │    │
│  └────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌────────────────────────────────────────────────────┐    │
│  │  MEMORY AGENT                                      │    │
│  │  save_brief() → core/db.py                        │    │
│  └────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
                            │
                            │ Data Operations
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    STORAGE LAYER                             │
│                                                              │
│  ┌──────────────────┐        ┌──────────────────┐          │
│  │   SQLite DB      │        │   FAISS Index    │          │
│  │   (core/db.py)   │        │   (core/embed.py)│          │
│  │                  │        │                  │          │
│  │ - meetings       │        │ - Embeddings     │          │
│  │ - materials      │        │ - Per-meeting    │          │
│  │ - briefs         │        │ - Vector search  │          │
│  └──────────────────┘        └──────────────────┘          │
└─────────────────────────────────────────────────────────────┘
```

---

## 🐛 Troubleshooting Tips

### Common Issues During Demo

**1. "No meeting selected" warning**
- **Cause:** User didn't select/create meeting
- **Fix:** Create or select meeting first
- **Backend:** `st.session_state.current_meeting_id` is None

**2. "No materials found"**
- **Cause:** No files uploaded yet
- **Fix:** Upload files before generating brief
- **Backend:** `db.get_materials()` returns empty list

**3. Brief generation fails**
- **Cause:** LLM API error or invalid JSON
- **Fix:** Check API key, retry
- **Backend:** JSON repair logic should handle most cases

**4. Q&A returns "No relevant context"**
- **Cause:** Question doesn't match materials semantically
- **Fix:** Try different question or add more materials
- **Backend:** FAISS search returns low similarity scores

**5. GPU not detected**
- **Cause:** No CUDA available
- **Fix:** System falls back to CPU automatically
- **Backend:** `core/embed.py:get_device()` detects CUDA

---

## 📊 Key Metrics to Highlight

During demo, mention:

1. **Speed:**
   - Embeddings: < 1 sec (GPU) / < 1 sec (CPU)
   - Brief generation: 5-15 seconds
   - Total pipeline: < 20 seconds

2. **Accuracy:**
   - Top-8 chunks retrieved (semantic search)
   - Source citations for every point
   - Cross-meeting memory for continuity

3. **Scalability:**
   - Per-meeting FAISS indexes
   - SQLite for structured data
   - GPU acceleration support

4. **AI Components:**
   - Neural network embeddings (SentenceTransformer)
   - Large Language Models (Gemini/GPT-4/Claude)
   - Semantic search (FAISS)

---

## 🎯 Demo Checklist

Before starting demo:

- [ ] API keys configured (.env file)
- [ ] Sample files ready (PDF/DOCX/TXT)
- [ ] Database initialized
- [ ] Embedding model preloaded
- [ ] GPU status visible (if applicable)
- [ ] Browser ready (full screen recommended)

During demo:

- [ ] Create meeting successfully
- [ ] Upload files with progress bar
- [ ] Generate brief (show all 5 sections)
- [ ] Show evidence citations
- [ ] Download brief (both formats)
- [ ] Recall previous brief
- [ ] Q&A example with sources
- [ ] Cross-meeting memory (if time)

---

## 📝 Notes for Presenter

**Key Talking Points:**

1. **"4 AI Agents"** - Emphasize each agent's role
2. **"Semantic Search"** - Not keyword matching, understands meaning
3. **"Cross-Meeting Memory"** - Continuity across recurring meetings
4. **"Source Citations"** - Every point is traceable
5. **"Multi-Provider"** - Works with Gemini, GPT-4, Claude

**Timing:**
- Full demo: 5-7 minutes
- Quick demo: 2 minutes
- Q&A: 2-3 minutes

**Audience Engagement:**
- Ask audience for meeting title
- Let them suggest questions for Q&A
- Show real-time processing (spinners, progress bars)

---

**End of Demo Guide**

