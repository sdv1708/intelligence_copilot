# Executive Intelligence Copilot — End‑to‑End Architecture & Implementation Plan (MVP, 4–5 Days)

**Goal:** Ship a realistic, minimal, and polished prototype that prepares **Meeting Briefs** from uploaded materials and a small “meeting memory” store. No over‑engineering. Everything below is implementable in 4–5 days and optimized for Cursor IDE usage.

---

## 0) TL;DR Scope

- **One-page app**: Upload files (PDF/DOCX/PPTX/TXT) or paste notes → click **Generate Brief** → show **Recap**, **Open Items**, **Key Topics**, **Agenda**, with evidence snippets.
- **Memory**: Save each brief to SQLite; “What happened last time?” fetches latest brief for a meeting.
- **Costs**: $0 using **Streamlit Cloud + Gemini 2.5 Flash Lite free tier + SQLite + FAISS**.
- **No external connectors** for MVP (Calendar/Slack/Jira are stretch goals).

---

## 1) System Diagram (MVP)

```
                 ┌─────────────────────────────┐
                 │    Frontend (Streamlit)     │
                 │  - Upload/Paste Materials   │
                 │  - Meeting Selector          │
                 │  - Generate Brief / Recall   │
                 └──────────────┬──────────────┘
                                │ (local call)
                                ▼
                 ┌─────────────────────────────┐
                 │    Orchestrator (Python)    │
                 │  - Ingest Agent             │
                 │  - Recall Agent             │
                 │  - Synthesis Agent (LLM)    │
                 │  - Persist Agent            │
                 └─────────┬─────────┬─────────┘
                           │         │
                   ┌───────┘         └───────────┐
                   ▼                             ▼
        ┌──────────────────────┐        ┌──────────────────────┐
        │  SQLite (briefs,     │        │  FAISS (vector idx)  │
        │  meetings, materials)│        │  + MiniLM embeddings  │
        └──────────────────────┘        └──────────────────────┘
                          ▲
                          │ (files & cache)
                          ▼
                   ┌───────────────┐
                   │  /data/raw    │
                   └───────────────┘
```

---
## 1.1 Multi-Agent Workflow Overview

The Executive Intelligence Copilot operates as a **multi-agent system** with four lightweight AI agents working in sequence:

| Agent | Role | Core Function |
|--------|------|----------------|
| **Ingestion Agent** | Parses and embeds new materials | Extracts text, chunks content, generates embeddings |
| **Recall Agent** | Retrieves past context | Finds relevant previous discussions and briefs |
| **Synthesis Agent** | Generates structured brief | Uses Gemini 2.5 Flash Lite/GPT-4/Claude 3.5 Sonnet to produce meeting summary JSON |
| **Memory Agent** | Stores and recalls meeting history | Saves briefs to SQLite and supports “What happened last time?” queries |

All four agents are executed in a linear workflow — no complex orchestration or concurrency required.


## 2) Tech Choices (Why)

- **UI**: Streamlit — deploys free, fast to build, looks clean.
- **LLM**: Gemini 2.5 Flash Lite (free tier) — good summarization & cost $0 for MVP. Also supports GPT-4 and Claude 3.5 Sonnet.
- **Embeddings**: `sentence-transformers/all-MiniLM-L6-v2` (local) — zero cost + good recall.
- **Vector store**: FAISS (local) — zero setup, performant.
- **DB**: SQLite — single-file store; perfect for single-user demo.
- **Runtime**: Single Python app (no extra services); deploy on Streamlit Cloud.

> Optional swap: if you prefer JavaScript SPA later, keep this API-compatible and move UI to Vercel; leave backend as is.

---

## 3) Repository Structure

```
executive-intelligence-copilot/
│
├── app.py                         # Streamlit UI (entrypoint)
│
├── core/
│   ├── __init__.py
│   ├── db.py                      # SQLite init + CRUD
│   ├── parsing.py                 # PDF/DOCX/PPTX/TXT extraction
│   ├── chunk.py                   # text chunking
│   ├── embed.py                   # MiniLM embeddings + FAISS index
│   ├── recall.py                  # top-k retrieval (meeting/global)
│   ├── synth.py                   # Gemini API call + prompts
│   ├── schema.py                  # Pydantic models (MeetingBrief, etc.)
│   └── utils.py                   # config, logging, ids, timers
│
├── prompts/
│   ├── system_prompt.txt      # Main brief generation (167 lines)
│   ├── user_prompt.txt        # User prompt template
│   ├── qa_system_prompt.txt   # Q&A system instructions
│   └── qa_user_prompt.txt     # Q&A user template
│
├── data/
│   ├── raw/                       # uploaded files and paste dumps
│   ├── faiss/                     # FAISS index files
│   └── briefs.db                  # SQLite database
│
├── sample_data/                   # AMI/Enron snippets + mock docs
│
├── .env.example                   # GEMINI_API_KEY, DB_PATH, FAISS_PATH
├── requirements.txt
├── README.md
└── LICENSE
```

---

## 4) Data Model (SQLite)

### 4.1 Tables

```sql
-- meetings
CREATE TABLE IF NOT EXISTS meetings (
  id TEXT PRIMARY KEY,
  title TEXT,
  date TEXT,
  attendees TEXT,     -- JSON string or CSV
  tags TEXT,          -- optional CSV
  created_at TEXT
);

-- materials (uploaded/pasted)
CREATE TABLE IF NOT EXISTS materials (
  id TEXT PRIMARY KEY,
  meeting_id TEXT,
  filename TEXT,
  media_type TEXT,    -- pdf, docx, pptx, txt, pasted
  text TEXT,
  created_at TEXT
);

-- briefs (final outputs)
CREATE TABLE IF NOT EXISTS briefs (
  id TEXT PRIMARY KEY,
  meeting_id TEXT,
  created_at TEXT,
  model TEXT,
  brief_json TEXT      -- serialized MeetingBrief
);
```

> `transcripts` table is optional for MVP; add later if you ingest audio/ASR.

### 4.2 Pydantic — `MeetingBrief`

```python
class ActionItem(BaseModel):
    owner: str
    item: str
    due: Optional[str] = None  # YYYY-MM-DD
    status: Literal["open", "blocked", "done"] = "open"

class AgendaItem(BaseModel):
    topic: str
    minutes: int
    owner: Optional[str] = None

class Evidence(BaseModel):
    source: str        # "material_id#chunk_idx"
    snippet: str

class MeetingBrief(BaseModel):
    meeting_title: str
    time_window: Optional[str] = None   # "2025-11-01..2025-11-07"
    last_meeting_recap: str
    open_action_items: List[ActionItem]
    key_topics_today: List[str]
    proposed_agenda: List[AgendaItem]
    evidence: List[Evidence]
```

---

## 5) API (Internal Functions)

For Streamlit we can call functions directly; if you prefer HTTP, wrap these in FastAPI later.

### 5.1 Ingestion

```python
def ingest_material(meeting_id: str, file_or_text) -> str:
    # 1) parse to text (by media type)
    # 2) chunk text
    # 3) embed chunks → upsert to FAISS (namespace=meeting_id)
    # 4) save material metadata/text to SQLite
    # returns material_id
```

### 5.2 Recall

```python
def recall_context(meeting_id: str, query: str = "", k: int = 8) -> List[Dict]:
    # search FAISS in namespace=meeting_id (fallback to global)
    # return [{text, material_id, chunk_idx, score} ...]
```

### 5.3 Synthesis

```python
def generate_brief(meeting_id: str, meeting_title: str, meeting_date: str) -> MeetingBrief:
    # Step 0: Check for previous meetings with same title (cross-meeting memory)
    previous_context = get_previous_meeting_context(meeting_id, meeting_title)
    
    # 1) fetch top-k context via recall_context()
    # 2) format prompts (include previous_context if available)
    # 3) call LLM (Gemini 2.5 Flash Lite/GPT-4/Claude 3.5 Sonnet) → JSON
    # 4) repair incomplete JSON if needed
    # 5) validate with Pydantic
    # 6) persist brief → SQLite
    # 7) return MeetingBrief
```

### 5.4 Memory/Recall

```python
def what_happened_last_time(meeting_id: str) -> Optional[MeetingBrief]:
    # return last saved brief for meeting_id (from briefs table)
```

---

## 6) Prompt Templates (copy/paste)

**`prompts/system_prompt.txt`**

```
You are Executive Intelligence Copilot. Produce a concise, executive-ready MeetingBrief.
Return VALID JSON matching the schema.
Be specific and actionable. Use only provided CONTEXT.
Prefer verbs, bullet points, and timeboxed agenda. If info is missing, add TODOs.
```

**`prompts/user_prompt.txt`**

```
MEETING_TITLE: {{title}}
MEETING_DATE: {{date}}

CONTEXT (top-k snippets with citations):
{{context_blocks}}

Task: Create a MeetingBrief JSON with fields:
- meeting_title
- time_window (if inferable)
- last_meeting_recap
- open_action_items [{owner,item,due?,status}]
- key_topics_today [string]
- proposed_agenda [{topic,minutes,owner?}] (≤ 45 total minutes unless specified)
- evidence [{source,snippet}]

Output ONLY JSON.
```

> **Evidence source format**: `"material_id#c{chunk_idx}"`

---

## 7) Streamlit UI Spec (Single Page)

- **Sidebar**
  - Select/Create Meeting (title, date, attendees CSV)
  - Buttons: **Upload/Paste Material**, **Generate Brief**, **What happened last time?**
- **Main**
  - Table: materials (filename, type, chars, added_at)
  - Output area:
    - Cards/accordions: **Recap**, **Open Items**, **Key Topics**, **Agenda**
    - Evidence chips w/ tooltips (snippet)
  - History dropdown: choose previous brief (optional)

> Use Streamlit `st.file_uploader`, `st.text_area`, `st.expander`, `st.dataframe`, `st.download_button`.

---

## 8) Implementation Order (5-Day Plan)

**Day 1 — Repo & Ingest**
- Scaffold repo + `requirements.txt`
- `core/db.py`: create tables + CRUD helpers
- `core/parsing.py`: handle pdf/docx/pptx/txt + pasted text
- `app.py`: create/select meeting, upload/paste material → display parsed text length

**Day 2 — Embedding & FAISS**
- `core/chunk.py`: 1,200-char chunks, 120 overlap
- `core/embed.py`: MiniLM embeddings; FAISS index per meeting_id (or namespaced)
- Upsert chunks on ingestion; basic recall function

**Day 3 — LLM Synthesis**
- `core/synth.py`: load prompts, build context blocks, call Gemini 1.5 Flash
- Parse/validate JSON → `MeetingBrief`
- Render brief nicely in Streamlit

**Day 4 — Memory & Recall UX**
- Persist brief to SQLite; history list
- Implement **What happened last time?**
- Add **Download Brief (.json/.md)**

**Day 5 — Polish & Deploy**
- Error handling (file parse, LLM failure, empty context)
- Token budget checks + rate-limit retries
- Deploy to Streamlit Cloud; add sample_data for demo

---

## 9) Requirements & Env

**`requirements.txt`**
```
streamlit
pydantic
sqlmodel
faiss-cpu
sentence-transformers
pypdf
python-docx
python-pptx
python-dotenv
google-generativeai
```
*(Optional fallback)*
```
openai
```

**`.env.example`**
```
GEMINI_API_KEY=your_key_here
DB_PATH=./data/briefs.db
FAISS_PATH=./data/faiss
```

---

## 10) Minimal Code Snippets (Cursor Starters)

**`core/chunk.py`**

```python
def chunk_text(txt: str, max_len=1200, overlap=120):
    chunks, i, n = [], 0, len(txt)
    while i < n:
        end = min(n, i + max_len)
        cut = txt.rfind(". ", i, end)
        if cut == -1 or cut < i + int(max_len * 0.6): cut = end
        chunks.append(txt[i:cut].strip())
        i = max(cut - overlap, i + 1)
    return [c for c in chunks if c]
```

**`core/embed.py`** (outline)

```python
from sentence_transformers import SentenceTransformer
import faiss, numpy as np, os, json

_model = None
def get_model():
    global _model
    if _model is None:
        _model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    return _model

def build_or_load_index(path: str, dim=384):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        return faiss.read_index(path)
    index = faiss.IndexFlatIP(dim)  # cosine via normalized vectors
    faiss.write_index(index, path)
    return index

def encode(chunks: list[str]):
    m = get_model()
    emb = m.encode(chunks, normalize_embeddings=True)
    return np.array(emb).astype("float32")
```

**`core/llm_providers.py`** (actual implementation)

```python
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic

def get_llm_provider(provider_name: str = "gemini"):
    if provider_name == "gemini":
        return ChatGoogleGenerativeAI(
            model="gemini-2.5-flash-lite",
            google_api_key=api_key,
            temperature=0.7,
            max_output_tokens=30000
        )
    elif provider_name == "openai":
        return ChatOpenAI(model="gpt-4", ...)
    elif provider_name == "anthropic":
        return ChatAnthropic(model="claude-3-5-sonnet-20241022", ...)
```

**Note:** Legacy `core/synth.py` exists but actual implementation uses LangChain via `agents/copilot_orchestrator.py`

---

## 11) Token Budgeting & Rate Limits (Reality Check)

- Use **top‑k = 8** chunks × ~200–300 tokens each → ~1.6–2.4k tokens input.
- Output brief target: **≤ 700 tokens**.
- With ~10–20 runs during dev, you’ll stay within Gemini free tier easily.
- Add retry with backoff on 429/5xx; show friendly UI message.

---

## 12) Error Handling (MVP-Level)

- **Parsing**: If a file fails, show “Couldn’t parse — try TXT/PDF” but keep others.
- **Empty context**: Warn and proceed with whatever is available; add TODOs in brief.
- **LLM failure**: Retry once; on failure, allow user to download raw context block.
- **DB write**: Wrap in try/except; log and continue (non-fatal).

---

## 13) Testing & Acceptance

**Happy-path test script:**
1. Create “AI Roadmap Sync” (date today).
2. Upload: 1 PDF + 1 TXT (email thread) from `sample_data/`.
3. Click **Generate Brief** → ensure all 4 sections populated.
4. Save brief → appears in History.
5. Click **What happened last time?** → returns the saved brief.
6. Download brief as JSON.

**Acceptance criteria:**
- Working end-to-end in ≤ 15 seconds for 2 files.
- JSON validates against `MeetingBrief` schema.
- Brief persists + recall works.
- UI is clean and demoable on Streamlit Cloud.

---

## 14) Deployment (Free)

- Push repo to GitHub.
- Go to **Streamlit Community Cloud** → New app → point to `app.py`.
- Add **Secrets**: `GEMINI_API_KEY`, `DB_PATH`, `FAISS_PATH`.
- Test with `sample_data/` (keep dataset small, <10 MB total).

---

## 15) Demo Script (2–3 minutes)

1. **Problem (15s):** Leaders spend hours prepping for meetings.
2. **Upload (30s):** Add a PDF + email thread.
3. **Generate (30s):** Show brief with Recap, Open Items, Topics, Agenda.
4. **Memory (20s):** “What happened last time?” → loads prior brief.
5. **Impact (20s):** “Reduced prep from ~2 hours to <10 minutes per meeting.”
6. **Close (15s):** Human-in-loop; AI assists, humans decide.

---

## 16) Stretch (Post‑MVP, Optional)

- `.ics` ingest for meetings
- Export brief to PDF
- Owner normalization (NER-style heuristics on names/emails)
- Simple tag-based search across all meetings

---

## 17) Build Checklist (Cursor‑Friendly)

- [ ] Create repo skeleton & `requirements.txt`
- [ ] Implement `db.py` (tables + CRUD)
- [ ] Implement `parsing.py` (PDF/DOCX/PPTX/TXT/paste)
- [ ] Implement `chunk.py`
- [ ] Implement `embed.py` (MiniLM + FAISS)
- [ ] Implement `recall.py` (top‑k, meeting namespace)
- [ ] Implement `schema.py` (Pydantic)
- [ ] Implement `synth.py` (Gemini call + prompts + Pydantic validate)
- [ ] Implement `app.py` (UI actions + rendering + downloads)
- [ ] Add `sample_data/` (emails, notes, small PDF)
- [ ] Deploy to Streamlit Cloud
- [ ] Run demo script & record timings

---

**Everything here is intentionally minimal, realistic, and achievable in 4–5 days.** 🚀
