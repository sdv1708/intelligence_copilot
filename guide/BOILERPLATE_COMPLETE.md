# ✅ Boilerplate Setup Complete

## What's Been Created

### 📁 Directory Structure
```
intelligence_copilot/
├── app.py                          (Streamlit UI - boilerplate ready)
├── requirements.txt                (All dependencies listed)
├── .env.example                    (Template for env vars)
├── .gitignore                      (Git ignore patterns)
├── SETUP_GUIDE.md                  (This setup instructions)
│
├── core/
│   ├── __init__.py
│   ├── schema.py                   (Pydantic models: ActionItem, AgendaItem, Evidence, MeetingBrief)
│   ├── utils.py                    (Logger, ID generation, timers)
│   ├── db.py                       (SQLite: meetings, materials, briefs tables + CRUD)
│   ├── parsing.py                  (PDF/DOCX/PPTX/TXT extraction)
│   ├── chunk.py                    (Text chunking: 1,200 char, 120 overlap)
│   ├── embed.py                    (MiniLM embeddings + FAISS index ops)
│   ├── recall.py                   (Vector search + context formatting)
│   └── synth.py                    (Gemini API + prompt templating + JSON validation)
│
├── prompts/
│   ├── system_prompt.txt           (System instructions for LLM)
│   └── user_prompt.txt             (User prompt with {{placeholders}})
│
├── data/
│   ├── raw/                        (Uploaded files will be stored here)
│   └── faiss/                      (FAISS index files per meeting)
│
└── sample_data/                    (For demo data - add files here later)
```

---

## 🎓 What You've Learned (Code Overview)

### **1. Data Model (`core/schema.py`)**
```python
class MeetingBrief(BaseModel):
    meeting_title: str
    last_meeting_recap: str
    open_action_items: List[ActionItem]
    key_topics_today: List[str]
    proposed_agenda: List[AgendaItem]
    evidence: List[Evidence]
```
→ **Why**: Structured validation before saving. Pydantic catches schema violations early.

### **2. Database (`core/db.py`)**
- Tables: `meetings`, `materials`, `briefs`
- CRUD functions for each table
- SQLite for simplicity (single-file DB, perfect for MVP)

→ **Why**: Persist meetings, materials, and generated briefs. Query them later for "What happened last time?"

### **3. Parsing (`core/parsing.py`)**
- PDF: `pypdf` library
- DOCX: `python-docx` library
- PPTX: `python-pptx` library
- TXT: direct decode
- Pasted text: textarea input

→ **Why**: Support multiple input formats. Fail gracefully on unsupported types.

### **4. Chunking (`core/chunk.py`)**
Split text into overlapping 1,200-character chunks at sentence boundaries.

→ **Why**: Manage token limits for LLM. Overlap preserves context across chunks.

### **5. Embeddings (`core/embed.py`)**
- Load `all-MiniLM-L6-v2` (384-dim embeddings)
- Create/load FAISS index (per-meeting or global)
- Encode chunks + add to index

→ **Why**: Convert text to vectors. Fast similarity search via FAISS.

### **6. Recall (`core/recall.py`)**
- Query embeddings against FAISS
- Return top-k chunks with scores
- Format as context blocks for LLM

→ **Why**: Find relevant context for a meeting. Foundation for RAG (Retrieval-Augmented Generation).

### **7. Synthesis (`core/synth.py`)**
- Load prompt templates
- Build user prompt with context
- Call Gemini 1.5 Flash API
- Parse JSON response
- Validate with Pydantic

→ **Why**: Generate structured briefs. Validation ensures data quality.

### **8. Utilities (`core/utils.py`)**
- Environment variable management
- Unique ID generation (with prefix + timestamp)
- Logging setup
- Performance timers

→ **Why**: Reusable patterns. Clean config management. Observability.

### **9. Streamlit UI (`app.py`)**
- Sidebar: Meeting selection, file upload, paste text
- Main: Output tabs, materials table
- Buttons: Generate Brief, Recall, Download

→ **Why**: User-friendly interface. Fast iteration on ideas.

---

## 🔄 Data Flow (The 5-Step Pipeline)

```
1. USER UPLOADS/PASTES
   ↓ (app.py)
2. PARSE FILE
   ↓ (parsing.py)
3. CHUNK TEXT
   ↓ (chunk.py)
4. EMBED & FAISS
   ↓ (embed.py + recall.py)
5. LLM SYNTHESIS
   ↓ (synth.py)
6. RENDER BRIEF
   ↓ (app.py)
7. PERSIST TO DB
   ↓ (db.py)
8. NEXT TIME: RECALL FROM DB
   ↓ (recall.py + db.py)
```

---

## 🚀 What's Next

### **Immediate (Setup)**
1. Create virtual environment: `python -m venv venv`
2. Activate: `venv\Scripts\activate` (Windows) or `source venv/bin/activate` (Mac/Linux)
3. Install: `pip install -r requirements.txt`
4. Create `.env` file from `.env.example` and add your Gemini API key
5. Test: `streamlit run app.py`

### **Day 1 Tasks (Wire Boilerplate)**
- [ ] Test Streamlit app runs without errors
- [ ] Wire "Create Meeting" form → save to SQLite via `db.py`
- [ ] Wire "Upload Files" → parse via `parsing.py` → show char count
- [ ] Wire "Paste Text" → save to SQLite
- [ ] Display materials table with filename, type, char count

### **Day 2 Tasks (Vector Search)**
- [ ] Test chunking: verify `chunk_text()` produces ~1,200 char chunks
- [ ] Test embeddings: `encode()` produces 384-dim vectors
- [ ] Test FAISS: add chunks, search, retrieve top-k
- [ ] Wire recall into Streamlit (optional: show retrieved chunks)

### **Day 3 Tasks (LLM)**
- [ ] Test Gemini API call with sample context
- [ ] Wire "Generate Brief" button → Gemini → JSON → Pydantic validation
- [ ] Render brief in tabs (Recap, Open Items, Topics, Agenda)

### **Day 4 Tasks (Memory)**
- [ ] Save brief to DB after generation
- [ ] Wire "What happened last time?" → fetch latest brief
- [ ] Add "Download Brief" (JSON + Markdown formats)

### **Day 5 Tasks (Polish)**
- [ ] Error handling for all failure modes
- [ ] Add retry logic for API calls
- [ ] Test end-to-end with sample data
- [ ] Deploy to Streamlit Cloud

---

## 💡 Key Concepts Reference

| Concept | Used In | Why |
|---------|---------|-----|
| **Chunking** | `chunk.py` | Break large texts into token-limited segments |
| **Embeddings** | `embed.py` | Convert text to vectors for similarity search |
| **FAISS Index** | `embed.py` + `recall.py` | Fast approximate nearest neighbor search |
| **RAG** | `recall.py` + `synth.py` | Retrieval-Augmented Generation: fetch context, feed to LLM |
| **Pydantic** | `schema.py` + `synth.py` | Schema validation: ensure data matches structure |
| **Prompt Templating** | `synth.py` | Use placeholders to build dynamic prompts |
| **SQLite CRUD** | `db.py` | Create, Read, Update, Delete operations on tables |

---

## 📚 Code Quality Notes

✅ **What we did right:**
- Clear module separation (parsing, embedding, synthesis, DB, UI)
- Docstrings on all functions
- Graceful error handling (log + return empty result)
- Lazy-load heavy models (embeddings only load when first used)
- Configurable via environment variables
- Type hints for clarity

🔧 **What we'll add incrementally:**
- Unit tests
- Integration tests
- Performance profiling
- Enhanced error messages for users
- Retry logic + rate-limit handling

---

## 🎯 Learning Milestones

By the end of this project, you'll understand:
1. **Streamlit**: Build interactive data apps quickly
2. **Embeddings**: Text-to-vector conversion + similarity search
3. **Vector Databases**: FAISS for efficient retrieval
4. **LLM Integration**: API calls, prompt engineering, JSON parsing
5. **SQLite**: Simple persistent storage for MVP
6. **Data Pipeline**: End-to-end flow from upload → brief

---

## ❓ Questions to Ask Yourself

As you implement each piece:
- **Parsing**: "Why does media_type matter?"
- **Chunking**: "Why overlaps? Why sentence boundaries?"
- **Embeddings**: "What does 384-dimensional mean?"
- **FAISS**: "How is this faster than brute-force search?"
- **Prompting**: "How do I get structured JSON from an LLM?"
- **Database**: "When do I write vs. read?"

We'll answer all of these as we code! 🚀

---

## 🎉 You're Ready!

All boilerplate is in place. The architecture is solid. The codebase is ready for your first integration.

**Next step: Activate your virtual environment and install dependencies.**

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

Then, say **"Ready for Day 1"** and we'll start wiring the UI! 💪

