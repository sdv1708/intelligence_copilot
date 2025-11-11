# Intelligence Copilot Branch Overview

## Executive Summary
- The Executive Intelligence Copilot prepares senior leaders for meetings by synthesizing uploaded or pasted materials into executive-ready briefs within a LangChain-driven multi-agent workflow.【F:context.md†L1-L22】【F:README.md†L1-L4】
- The project has completed its first five implementation phases, including Q&A capabilities, and is entering a testing and deployment focus.【F:context.md†L3-L94】

## System Architecture
- **Streamlit Frontend (`app.py`):** Provides the premium UI, initializes cached resources (database, orchestrator, embeddings), and manages meeting creation, material ingestion, brief visualization, downloads, and the interactive Q&A experience.【F:app.py†L21-L194】【F:app.py†L247-L400】【F:app.py†L418-L600】
- **Agent Layer (`agents/copilot_orchestrator.py`):** Coordinates ingestion, recall, synthesis, and memory steps while handling retries, JSON repair, and Q&A prompts via LangChain chat models.【F:agents/copilot_orchestrator.py†L18-L399】【F:agents/copilot_orchestrator.py†L402-L588】
- **Core Services (`core/`):** Supply document parsing, chunking, embedding, retrieval, schema validation, database persistence, provider selection, and shared utilities.【F:core/parsing.py†L1-L92】【F:core/chunk.py†L1-L45】【F:core/embed.py†L1-L157】【F:core/recall.py†L1-L126】【F:core/schema.py†L2-L38】【F:core/db.py†L1-L288】【F:core/llm_providers.py†L1-L57】【F:core/utils.py†L1-L94】
- **Prompt Templates (`prompts/`):** Define executive-focused instructions for brief generation and the Q&A advisor persona, ensuring consistent tone and JSON compliance.【F:prompts/system_prompt.txt†L1-L45】【F:prompts/user_prompt.txt†L1-L85】【F:prompts/qa_system_prompt.txt†L1-L42】【F:prompts/qa_user_prompt.txt†L1-L47】

## Data Model & Persistence
- SQLite stores meetings, materials, and generated briefs with schema initialization, CRUD helpers, and brief history retrieval through `Database`. Meeting and material records are timestamped and linked, while briefs track provider metadata and serialized content.【F:core/db.py†L10-L288】
- Pydantic models capture MeetingBrief structure (recap, action items, key topics, agenda, evidence) and associated sub-records (ActionItem, AgendaItem, Evidence).【F:core/schema.py†L8-L37】

## Processing Pipeline
1. **Ingestion:** Materials are parsed, chunked, embedded, and indexed in FAISS per meeting, returning metadata about stored chunks.【F:agents/copilot_orchestrator.py†L28-L80】【F:core/parsing.py†L8-L92】【F:core/chunk.py†L7-L45】【F:core/embed.py†L39-L157】
2. **Recall:** On-demand retrieval loads meeting materials, recreates chunk metadata, builds or loads a FAISS index, and surfaces top-k snippets formatted with citations.【F:core/recall.py†L9-L126】【F:agents/copilot_orchestrator.py†L82-L116】
3. **Synthesis:** Prompt templates assemble system and user messages; the orchestrator invokes the configured LLM with retries, JSON cleanup, and schema validation before saving the brief to SQLite.【F:agents/copilot_orchestrator.py†L195-L388】【F:core/llm_providers.py†L9-L57】【F:core/db.py†L213-L228】
4. **Memory:** Generated briefs persist via `save_brief`, enabling later recall of the most recent or historical versions and feeding cross-meeting context.【F:core/db.py†L213-L288】【F:agents/copilot_orchestrator.py†L117-L194】【F:agents/copilot_orchestrator.py†L394-L400】

## Interactive Q&A Flow
- The Streamlit UI gates Q&A on meeting selection and available materials, captures questions, and displays conversation history with cited sources.【F:app.py†L247-L323】
- Orchestrator-level Q&A reuses recall to target top five chunks, builds dedicated QA prompts, queries the LLM, and extracts citations from context blocks.【F:agents/copilot_orchestrator.py†L402-L468】

## Retrieval & Embedding Details
- SentenceTransformer embeddings are GPU-aware and normalized, with adaptive batch sizing and FAISS index persistence for cosine similarity search.【F:core/embed.py†L14-L157】
- Retrieval pipelines rebuild chunk metadata on demand, ensure FAISS indexes exist, and guard against empty datasets with logging hooks.【F:core/recall.py†L24-L103】

## Configuration & Utilities
- Utilities provide environment-variable access, consistent logging, ID generation, timing decorators, and environment-aware storage paths supporting Streamlit Cloud temp directories and local data folders.【F:core/utils.py†L1-L94】
- `.env` defaults (provider selection, API keys, storage paths) are documented in the project context to facilitate deployment across providers.【F:context.md†L139-L213】

## User Experience Highlights
- The UI emphasizes executive polish with custom styling, session state management, meeting CRUD, material uploads/paste workflows, brief rendering with expanders, download toggles, and device badges for GPU detection.【F:app.py†L21-L399】【F:app.py†L418-L600】
- Markdown conversion of briefs includes status icons, evidence excerpts, and agenda summaries for sharing outside the app.【F:app.py†L196-L244】

## Prompts & Governance
- Brief generation prompts enforce strict JSON output while guiding the LLM through strategic meeting analysis across recap, actions, topics, agenda, and evidence sections.【F:prompts/system_prompt.txt†L1-L45】【F:prompts/user_prompt.txt†L1-L85】
- Q&A prompts position the assistant as a trusted chief of staff, encouraging actionable narratives with bolded highlights and strategic recommendations.【F:prompts/qa_system_prompt.txt†L1-L42】【F:prompts/qa_user_prompt.txt†L1-L47】

## Current Status & Next Steps
- Implementation phases 1–7 are complete, covering database setup, embeddings, LLM synthesis, multi-agent orchestration, memory UX, and Q&A. The immediate roadmap focuses on comprehensive testing, performance tuning, and deployment readiness.【F:context.md†L25-L136】【F:context.md†L225-L276】

