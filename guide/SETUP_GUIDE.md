# Executive Intelligence Copilot — Setup Guide

## ✅ Boilerplate Created

All files and directories have been scaffolded according to the architecture document.

### Directory Structure
```
executive-intelligence-copilot/
├── app.py                          # Streamlit UI (entry point)
├── requirements.txt                # Python dependencies
├── .env.example                    # Environment variables template
├── .env                            # Your local config (create from .env.example)
├── .gitignore
│
├── core/
│   ├── __init__.py
│   ├── schema.py                   # Pydantic models
│   ├── utils.py                    # Config, logging, IDs
│   ├── db.py                       # SQLite CRUD
│   ├── parsing.py                  # PDF/DOCX/PPTX/TXT parsing
│   ├── chunk.py                    # Text chunking
│   ├── embed.py                    # Embeddings + FAISS
│   ├── recall.py                   # Vector search
│   └── synth.py                    # LLM synthesis
│
├── prompts/
│   ├── system_prompt.txt           # System instructions
│   └── user_prompt.txt             # User prompt template
│
├── data/
│   ├── raw/                        # Uploaded files
│   └── faiss/                      # FAISS indexes
│
└── sample_data/                    # Demo files (optional)
```

---

## 🚀 Quick Start

### 1. Create Virtual Environment
```bash
python -m venv venv
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Set Up Environment Variables
Copy `.env.example` to `.env` and fill in your API key:
```bash
# .env
GEMINI_API_KEY=your_actual_gemini_api_key
DB_PATH=./data/briefs.db
FAISS_PATH=./data/faiss
```

### 4. Run the App
```bash
streamlit run app.py
```

The app will open at `http://localhost:8501`

---

## 📚 Learning Path (5-Day Plan)

### **Day 1: Repo & Ingest (✅ BOILERPLATE COMPLETE)**
- [x] Scaffold repo + `requirements.txt`
- [x] Create database schema in `core/db.py`
- [x] Implement parsing in `core/parsing.py`
- [ ] **Next**: Wire UI to create/select meetings, upload/paste materials

**Learning Focus**: Streamlit basics, SQLite CRUD, file parsing

---

### **Day 2: Embedding & FAISS**
- [ ] Finalize `core/chunk.py` (chunking logic)
- [ ] Implement `core/embed.py` (MiniLM embeddings)
- [ ] Build FAISS indexing per meeting
- [ ] Test recall functionality in `core/recall.py`

**Learning Focus**: Embeddings, vector similarity, FAISS operations

---

### **Day 3: LLM Synthesis**
- [ ] Complete `core/synth.py` (Gemini integration)
- [ ] Load and render brief in UI
- [ ] Handle JSON validation with Pydantic

**Learning Focus**: LLM prompting, JSON handling, error handling

---

### **Day 4: Memory & Recall UX**
- [ ] Persist briefs to SQLite
- [ ] Implement "What happened last time?" feature
- [ ] Add download (JSON/Markdown)

**Learning Focus**: State management, UX patterns

---

### **Day 5: Polish & Deploy**
- [ ] Error handling + retries
- [ ] Token budget tracking
- [ ] Deploy to Streamlit Cloud

**Learning Focus**: Production readiness, monitoring

---

## 🧪 Boilerplate Code Overview

### **Core Modules**

#### `core/schema.py`
- **ActionItem**: Owner, item description, due date, status
- **AgendaItem**: Topic, duration, owner
- **Evidence**: Source reference, snippet
- **MeetingBrief**: Complete brief structure

#### `core/db.py`
Database CRUD operations:
- `create_meeting()`: Add new meeting
- `add_material()`: Attach file/text to meeting
- `save_brief()`: Persist generated brief
- `get_latest_brief()`: Fetch last brief for meeting

#### `core/parsing.py`
File format handlers:
- `parse_pdf()`, `parse_docx()`, `parse_pptx()`, `parse_txt()`
- `parse_file()`: Auto-detect format
- `parse_pasted_text()`: Handle textarea input

#### `core/chunk.py`
- `chunk_text()`: Split text into overlapping 1,200-char chunks
- Respects sentence boundaries for coherence

#### `core/embed.py`
- `get_model()`: Load MiniLM embeddings (lazy)
- `build_or_load_index()`: FAISS index management
- `encode()`: Convert text to embeddings
- `search_index()`: Top-k vector search

#### `core/recall.py`
- `recall_context()`: Retrieve relevant chunks for a meeting
- `format_context_blocks()`: Format results for LLM prompt

#### `core/synth.py`
- `call_gemini()`: LLM API call
- `build_user_prompt()`: Template substitution
- `generate_brief()`: End-to-end brief generation

#### `core/utils.py`
- `get_env()`: Safe environment variable access
- `generate_id()`: Unique ID generation
- `timer()`: Performance decorator
- Logging setup

### **Streamlit UI (`app.py`)**
Boilerplate sections:
- Meeting creation/selection sidebar
- Material upload and paste areas
- Action buttons (Generate, Recall, Download)
- Output tabs (Recap, Open Items, Topics, Agenda)

---

## 🎯 Next Steps

When you're ready to proceed:

1. **Activate your virtual environment**
2. **Install dependencies** (`pip install -r requirements.txt`)
3. **Create `.env` file** with your Gemini API key
4. **Test the basic app** (`streamlit run app.py`)

Then, we'll implement the database integration and file parsing step-by-step.

---

## 📖 Key Concepts

### **Chunking**
Breaking large documents into overlapping segments to preserve context while managing token limits.

### **Embeddings**
Converting text to numerical vectors (384-dim for MiniLM) that capture semantic meaning.

### **FAISS Index**
Fast approximate nearest neighbor search for finding relevant chunks.

### **Pydantic**
Schema validation: ensures briefs match our `MeetingBrief` structure before saving.

### **Prompt Engineering**
Carefully formatted templates (system + user) to guide the LLM toward structured JSON output.

---

## 💡 Tips for Learning

- **Read code comments**: Every function has docstrings explaining its purpose.
- **Trace the data flow**: Follow a document from upload → parse → chunk → embed → search → synthesize.
- **Test incrementally**: After each day, run a small test to verify the pipeline works.
- **Ask questions**: Each component teaches a specific skill; we'll explain as we code.

---

**Ready to start Day 1 implementation? Say "Go to Day 1" and we'll wire up the UI! 🚀**

