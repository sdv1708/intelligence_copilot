# Implementation Checklist

## ✅ Boilerplate (COMPLETE)

### Repository Structure
- [x] Create directory tree
- [x] Create all core modules
- [x] Create prompts directory
- [x] Create data directories
- [x] Create sample_data directory

### Core Modules
- [x] `core/__init__.py`
- [x] `core/schema.py` - Pydantic models
- [x] `core/utils.py` - Config, logging, ID generation
- [x] `core/db.py` - SQLite CRUD operations
- [x] `core/parsing.py` - PDF/DOCX/PPTX/TXT parsing
- [x] `core/chunk.py` - Text chunking logic
- [x] `core/embed.py` - Embeddings + FAISS
- [x] `core/recall.py` - Vector search
- [x] `core/synth.py` - LLM integration

### Configuration Files
- [x] `requirements.txt` - All dependencies
- [x] `.env.example` - Environment template
- [x] `.gitignore` - Git exclusions
- [x] `app.py` - Boilerplate Streamlit UI

### Prompt Templates
- [x] `prompts/system_prompt.txt` - System instructions
- [x] `prompts/user_prompt.txt` - User prompt template

### Documentation
- [x] `SETUP_GUIDE.md` - Setup instructions
- [x] `BOILERPLATE_COMPLETE.md` - What was created
- [x] `IMPLEMENTATION_CHECKLIST.md` - This file

---

## 📋 Day 1: Repo & Ingest (NEXT)

### Database Integration
- [ ] Test `Database.init_db()` creates tables
- [ ] Test `Database.create_meeting()` works
- [ ] Test `Database.add_material()` works
- [ ] Verify SQLite file created at `data/briefs.db`

### UI - Meeting Management
- [ ] Wire "Create New Meeting" form
- [ ] Save meeting to DB via button click
- [ ] Wire "Select Existing Meeting" dropdown
- [ ] Load meetings from DB into dropdown
- [ ] Display selected meeting details

### UI - File Upload/Paste
- [ ] Wire `st.file_uploader` to parsing pipeline
- [ ] Test PDF parsing
- [ ] Test DOCX parsing
- [ ] Test PPTX parsing
- [ ] Test TXT parsing
- [ ] Display parsed character count
- [ ] Save parsed text to DB via `add_material()`

### UI - Pasted Text
- [ ] Wire `st.text_area` to parsing
- [ ] Parse pasted text via `parse_pasted_text()`
- [ ] Display character count
- [ ] Save to DB

### Materials Display
- [ ] Fetch materials for meeting from DB
- [ ] Display as table: filename, type, char count, created_at
- [ ] Sort by created_at descending

### Testing
- [ ] Create test meeting "AI Roadmap Sync"
- [ ] Upload PDF from sample_data
- [ ] Upload TXT from sample_data
- [ ] See materials appear in table
- [ ] Verify data in briefs.db

---

## 📋 Day 2: Embedding & FAISS

### Chunking
- [ ] Test `chunk_text()` on sample material
- [ ] Verify ~1,200 char chunks
- [ ] Verify overlaps work
- [ ] Verify sentence boundary preservation

### Embeddings
- [ ] Test `get_model()` loads without errors
- [ ] Test `encode()` on sample text
- [ ] Verify embeddings are 384-dimensional
- [ ] Verify normalization (magnitude ~1.0)

### FAISS Index
- [ ] Test `build_or_load_index()` creates index
- [ ] Test `add_to_index()` adds embeddings
- [ ] Verify index file created at `data/faiss/{meeting_id}.index`
- [ ] Test loading existing index

### Recall
- [ ] Test `recall_context()` returns chunks with scores
- [ ] Test top-k filtering (k=8)
- [ ] Test `format_context_blocks()` output format
- [ ] Verify source citations are correct

### UI Integration (Optional Day 2)
- [ ] Add "Preview Context" button in UI
- [ ] Show retrieved chunks with sources
- [ ] Display similarity scores

### Testing
- [ ] Generate 100 chunks from uploaded material
- [ ] Verify FAISS index has 100 entries
- [ ] Search for relevant chunk
- [ ] Verify top result is correct

---

## 📋 Day 3: LLM Synthesis

### Prompts
- [ ] Load system_prompt.txt
- [ ] Load user_prompt.txt
- [ ] Test template substitution {{placeholders}}
- [ ] Verify format is correct

### Gemini Integration
- [ ] Set GEMINI_API_KEY in .env
- [ ] Test `call_gemini()` with simple prompt
- [ ] Verify response parsing (extract JSON from markdown if needed)
- [ ] Test error handling (no API key, invalid response)

### Brief Generation
- [ ] Test `generate_brief()` end-to-end
- [ ] Verify Pydantic validation passes
- [ ] Test with multiple chunk contexts
- [ ] Test with empty context (graceful degradation)

### UI - Brief Display
- [ ] Wire "Generate Brief" button
- [ ] Display MeetingBrief in tabs:
  - [ ] Recap tab
  - [ ] Open Items tab (list ActionItems)
  - [ ] Key Topics tab (list topics)
  - [ ] Agenda tab (list with duration)
- [ ] Display evidence chips with snippets
- [ ] Show loading spinner during generation

### Error Handling
- [ ] Handle API quota exceeded (429)
- [ ] Handle malformed JSON response
- [ ] Handle validation errors
- [ ] Show user-friendly error messages

### Testing
- [ ] Generate brief for sample meeting
- [ ] Verify all 4 sections populated
- [ ] Verify evidence sources are correct
- [ ] Verify action items have owners

---

## 📋 Day 4: Memory & Recall UX

### Brief Persistence
- [ ] Test `Database.save_brief()` stores JSON
- [ ] Verify brief_id generated
- [ ] Verify created_at timestamp recorded
- [ ] Test `Database.get_brief_by_id()` retrieval

### History Management
- [ ] Test `Database.get_brief_history()` returns all briefs
- [ ] Sort by created_at descending
- [ ] Test `Database.get_latest_brief()` returns most recent

### UI - What Happened Last Time?
- [ ] Wire "What happened last time?" button
- [ ] Fetch latest brief for meeting
- [ ] Display in same format as generated brief
- [ ] Show timestamp of previous meeting

### UI - History Dropdown
- [ ] Add dropdown to select previous brief
- [ ] Load and display selected brief
- [ ] Show generation model and date

### Downloads
- [ ] Download brief as JSON
- [ ] Download brief as Markdown
- [ ] Test file download works
- [ ] Verify formats are readable

### Testing
- [ ] Generate and save brief #1
- [ ] Generate and save brief #2
- [ ] Click "What happened last time?" → get brief #1
- [ ] Download both formats
- [ ] Verify downloads are valid

---

## 📋 Day 5: Polish & Deploy

### Error Handling
- [ ] Add try/except around all DB operations
- [ ] Add try/except around file parsing
- [ ] Add try/except around LLM calls
- [ ] Show friendly error messages in UI
- [ ] Log all errors

### Retry Logic
- [ ] Implement exponential backoff for API calls
- [ ] Retry on 429 (rate limit) with backoff
- [ ] Retry on 5xx errors (max 3 attempts)
- [ ] Show retry progress to user

### Token Budgeting
- [ ] Calculate input tokens before calling LLM
- [ ] Limit context chunks if approaching limit
- [ ] Display token usage to user (optional)
- [ ] Add warning if approaching quota

### Sample Data
- [ ] Create sample meeting
- [ ] Upload sample PDF
- [ ] Upload sample TXT email
- [ ] Pre-generate sample brief
- [ ] Document in README

### UI Polish
- [ ] Add loading spinners
- [ ] Add success/error toasts
- [ ] Improve layout and spacing
- [ ] Test responsive design
- [ ] Add helpful tooltips/hints

### Documentation
- [ ] Update README with features
- [ ] Add demo screenshots
- [ ] Document API/functions
- [ ] Create troubleshooting guide

### Testing (Happy Path)
1. [ ] Open app at localhost:8501
2. [ ] Create "Demo Meeting" (date today)
3. [ ] Upload sample PDF
4. [ ] Upload sample TXT email
5. [ ] Click "Generate Brief"
6. [ ] Verify brief generated in <15 seconds
7. [ ] Check all 4 sections populated
8. [ ] Click "Download Brief"
9. [ ] Close app, reopen
10. [ ] Click "What happened last time?"
11. [ ] Verify same brief loads

### Deployment (Streamlit Cloud)
- [ ] Create GitHub repository
- [ ] Push code to GitHub
- [ ] Go to streamlit.io/cloud
- [ ] Create new app → point to GitHub repo
- [ ] Add Secrets: GEMINI_API_KEY
- [ ] Test on Cloud URL
- [ ] Create demo video (2-3 min)

### Production Readiness
- [ ] Performance profiling (latency, memory)
- [ ] Cost analysis (API calls per user)
- [ ] Concurrency testing
- [ ] Edge case handling
- [ ] Security review (no hardcoded keys, etc.)

---

## 📊 Success Metrics

### Performance
- [ ] Brief generation: ≤ 15 seconds (2 files)
- [ ] File upload: immediate
- [ ] Database queries: <100ms
- [ ] UI responsiveness: smooth

### Quality
- [ ] All briefs validate against MeetingBrief schema
- [ ] Error rate: <1%
- [ ] Evidence snippets are accurate
- [ ] Action items have owners

### User Experience
- [ ] Create new meeting in <10 seconds
- [ ] Upload files and generate brief in <20 seconds
- [ ] "What happened last time?" instant (<2 sec)
- [ ] All buttons have clear labels
- [ ] No crashes or hangs

---

## 🎯 Final Demo Script (2-3 minutes)

1. **Problem (15s)**: Leaders spend hours prepping for meetings
2. **Solution intro (20s)**: Show app UI
3. **Demo upload (30s)**: Upload PDF + TXT email
4. **Demo generation (30s)**: Click "Generate Brief" → show output
5. **Demo memory (30s)**: Click "What happened last time?"
6. **Demo download (15s)**: Download as JSON/Markdown
7. **Impact (20s)**: Reduced prep time from 2 hours to 5 minutes
8. **Close (15s)**: AI assists, humans decide

---

## Notes

- **Requirements may change**: Update this checklist as needed
- **Iterate, don't perfect**: Ship working features first
- **Test continuously**: Run happy-path test after each day
- **Save often**: Commit to Git frequently
- **Ask questions**: Each feature teaches a concept

---

**Start Date**: November 7, 2025  
**Target Completion**: November 11/12, 2025 (4-5 days)  
**Status**: ✅ Boilerplate Complete → **Ready for Day 1 Implementation**

