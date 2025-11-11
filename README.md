# Executive Intelligence Copilot

A production-grade AI system that automates executive meeting preparation through intelligent document analysis, semantic search, and multi-agent orchestration. Transforms hours of manual preparation into minutes of automated briefing generation.

---

## Overview

Executive Intelligence Copilot is a sophisticated multi-agent AI system designed to analyze meeting materials, extract actionable insights, and generate executive-ready briefs. Built with enterprise-grade architecture patterns, the system leverages neural networks for semantic understanding, vector search for intelligent retrieval, and large language models for content synthesis.

**Core Value Proposition:** Reduce executive meeting preparation time from 2+ hours to under 10 minutes while improving information accuracy and traceability through source citations.

---

## Architecture

### Multi-Agent System Design

The system implements a four-agent orchestration pattern using LangChain, where each agent specializes in a distinct phase of the document processing pipeline:

```
┌─────────────────────────────────────────────────────────────┐
│                    Orchestration Layer                       │
│              (agents/copilot_orchestrator.py)               │
└─────────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
        ▼                   ▼                   ▼
┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│  Ingestion   │   │    Recall    │   │  Synthesis   │
│    Agent     │   │    Agent     │   │    Agent     │
└──────────────┘   └──────────────┘   └──────────────┘
        │                   │                   │
        └───────────────────┼───────────────────┘
                            │
                            ▼
                    ┌──────────────┐
                    │   Memory     │
                    │    Agent     │
                    └──────────────┘
```

**Agent Responsibilities:**

1. **Ingestion Agent**: Parses documents (PDF, DOCX, PPTX, TXT), chunks text intelligently, generates semantic embeddings using SentenceTransformer neural networks, and indexes content in FAISS for vector search.

2. **Recall Agent**: Performs semantic similarity search across meeting materials using FAISS, retrieves top-k relevant chunks based on query context, and formats retrieved content with source citations.

3. **Synthesis Agent**: Orchestrates LLM interactions via LangChain abstraction layer, builds context-aware prompts with cross-meeting memory integration, parses and validates structured JSON responses, and implements robust error handling with JSON repair logic.

4. **Memory Agent**: Persists generated briefs to SQLite with full audit trail, enables historical brief retrieval, and supports cross-meeting context injection for recurring meetings.

### Technical Stack

**Core Framework:**
- **LangChain 0.3.7**: Multi-agent orchestration and LLM abstraction layer
- **Streamlit 1.39.0**: Production-grade web interface
- **Pydantic 2.9.0**: Type-safe data validation and serialization

**Machine Learning & AI:**
- **SentenceTransformers 3.3.0**: Neural network embeddings (all-MiniLM-L6-v2, 384-dimensional)
- **FAISS-CPU 1.9.0**: High-performance vector similarity search
- **LangChain Providers**: Multi-cloud LLM support (Gemini 2.5 Flash Lite, GPT-4, Claude 3.5 Sonnet)

**Data Layer:**
- **SQLite**: Relational database for structured data persistence
- **FAISS**: Vector database for semantic search indices

**Document Processing:**
- **PyPDF 5.1.0**: PDF text extraction
- **python-docx 1.1.2**: Microsoft Word document parsing
- **python-pptx 1.0.2**: PowerPoint presentation extraction

---

## Key Features

### Intelligent Document Processing
- Multi-format support: PDF, DOCX, PPTX, TXT with robust parsing
- Intelligent text chunking with sentence-boundary awareness (1200 char chunks, 120 char overlap)
- GPU-accelerated embedding generation with automatic CPU fallback
- Per-meeting vector index isolation for data privacy

### Semantic Search & Retrieval
- Neural network-powered semantic search (not keyword-based)
- Top-k retrieval with similarity scoring
- Context-aware query processing
- Source citation tracking (material_id#chunk_idx format)

### AI-Powered Brief Generation
- Multi-provider LLM support (Gemini, OpenAI, Anthropic) with seamless switching
- Cross-meeting memory for recurring meeting continuity
- Structured output generation with JSON schema validation
- Robust error handling with automatic JSON repair
- Field-level validation with intelligent defaults

### Enterprise Features
- Complete audit trail (meeting history, brief versions, model tracking)
- Export capabilities (JSON, Markdown formats)
- Interactive Q&A interface with conversation history
- Source attribution for every generated insight
- Professional logging with structured error handling

---

## Installation

### Prerequisites

- Python 3.11+
- pip package manager
- CUDA-capable GPU (optional, for accelerated embeddings)

### Setup

1. **Clone the repository**
```bash
git clone <repository-url>
cd intelligence_copilot
```

2. **Create virtual environment**
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

4. **Configure environment variables**

Create a `.env` file in the project root:

```env
# LLM Provider Selection (gemini, openai, or anthropic)
LLM_PROVIDER=gemini

# API Keys (provide the one matching LLM_PROVIDER)
GEMINI_API_KEY=your_gemini_api_key_here
OPENAI_API_KEY=your_openai_api_key_here
ANTHROPIC_API_KEY=your_anthropic_api_key_here

# Data Storage Paths (optional, defaults shown)
DB_PATH=./data/briefs.db
FAISS_PATH=./data/faiss
```

5. **Initialize data directories**
```bash
mkdir -p data/faiss data/raw
```

### Verification

Run the application:
```bash
streamlit run app.py
```

The application will initialize the database schema automatically on first run.

---

## Usage

### Basic Workflow

1. **Create or Select Meeting**
   - Use sidebar to create new meeting or select existing
   - Provide meeting metadata (title, date, attendees, tags)

2. **Upload Materials**
   - Upload documents (PDF, DOCX, PPTX, TXT) or paste text content
   - System automatically processes and indexes materials

3. **Generate Brief**
   - Click "Generate Brief" to trigger multi-agent pipeline
   - System retrieves relevant context, synthesizes brief, and saves to database

4. **Review & Export**
   - Review generated brief across five sections: Recap, Action Items, Topics, Agenda, Evidence
   - Export brief in JSON or Markdown format
   - Access brief history for version comparison

### Advanced Features

**Cross-Meeting Memory:**
When creating a meeting with the same title as a previous meeting, the system automatically injects context from the prior meeting, including action items and key topics.

**Interactive Q&A:**
Use the Q&A interface to ask natural language questions about uploaded materials. The system performs semantic search to find relevant context and generates answers with source citations.

**Brief History:**
Access all previously generated briefs for a meeting through the history dropdown. Each brief includes timestamp and model provider information.

---

## Architecture Deep Dive

### Data Flow

```
Document Upload
    ↓
[Ingestion Agent]
    ├─ Parse document → Extract text
    ├─ Chunk text (1200 chars, 120 overlap)
    ├─ Generate embeddings (384-dim vectors)
    └─ Index in FAISS (per-meeting namespace)
    ↓
Material stored in SQLite + FAISS indexed
    ↓
[Recall Agent] (on brief generation)
    ├─ Query FAISS for top-8 relevant chunks
    ├─ Format context blocks with citations
    └─ Return formatted context
    ↓
[Synthesis Agent]
    ├─ Check for previous meetings (cross-meeting memory)
    ├─ Build prompts with context
    ├─ Call LLM (Gemini/GPT-4/Claude)
    ├─ Parse JSON response
    ├─ Repair incomplete JSON (if needed)
    └─ Validate against Pydantic schema
    ↓
[Memory Agent]
    ├─ Serialize MeetingBrief to JSON
    └─ Persist to SQLite
    ↓
Brief displayed in UI
```

### Database Schema

**meetings**
- `id` (TEXT PRIMARY KEY): Unique meeting identifier
- `title` (TEXT NOT NULL): Meeting title
- `date` (TEXT): Meeting date (ISO format)
- `attendees` (TEXT): Comma-separated attendee list
- `tags` (TEXT): Comma-separated tags
- `created_at` (TEXT NOT NULL): Creation timestamp

**materials**
- `id` (TEXT PRIMARY KEY): Unique material identifier
- `meeting_id` (TEXT FOREIGN KEY): Reference to meetings table
- `filename` (TEXT): Original filename
- `media_type` (TEXT): Format (pdf, docx, pptx, txt, pasted)
- `text` (TEXT): Extracted text content
- `created_at` (TEXT NOT NULL): Upload timestamp

**briefs**
- `id` (TEXT PRIMARY KEY): Unique brief identifier
- `meeting_id` (TEXT FOREIGN KEY): Reference to meetings table
- `created_at` (TEXT NOT NULL): Generation timestamp
- `model` (TEXT): LLM provider used (gemini/openai/anthropic)
- `brief_json` (TEXT NOT NULL): Serialized MeetingBrief (JSON)

### Vector Search Architecture

The system uses FAISS (Facebook AI Similarity Search) for efficient vector similarity search:

- **Index Type**: IndexFlatIP (Inner Product for cosine similarity on normalized vectors)
- **Embedding Dimension**: 384 (all-MiniLM-L6-v2 model)
- **Index Isolation**: Per-meeting namespace (separate index per meeting_id)
- **Retrieval Strategy**: Top-k similarity search (default k=8 for briefs, k=5 for Q&A)

### LLM Provider Abstraction

The system implements a provider abstraction layer via LangChain, enabling seamless switching between LLM providers:

- **Google Gemini 2.5 Flash Lite**: Default provider, optimized for speed and cost
- **OpenAI GPT-4**: High-quality output for complex synthesis tasks
- **Anthropic Claude 3.5 Sonnet**: Specialized for structured output generation

Provider selection is configured via environment variable (`LLM_PROVIDER`), with runtime switching supported through orchestrator initialization.

---

## Project Structure

```
intelligence_copilot/
├── agents/
│   └── copilot_orchestrator.py      # Multi-agent orchestration layer
│
├── core/
│   ├── db.py                         # SQLite database operations
│   ├── parsing.py                    # Document parsing (PDF/DOCX/PPTX/TXT)
│   ├── chunk.py                      # Text chunking logic
│   ├── embed.py                      # Embedding generation + FAISS management
│   ├── recall.py                      # Vector search + context formatting
│   ├── llm_providers.py              # LLM provider factory (LangChain)
│   ├── schema.py                     # Pydantic data models
│   ├── synth.py                      # Legacy synthesis (deprecated)
│   └── utils.py                      # Utilities (logging, config, ID generation)
│
├── prompts/
│   ├── system_prompt.txt             # Main brief generation system prompt
│   ├── user_prompt.txt               # User prompt template
│   ├── qa_system_prompt.txt          # Q&A system prompt
│   └── qa_user_prompt.txt            # Q&A user prompt template
│
├── data/
│   ├── briefs.db                     # SQLite database
│   ├── faiss/                        # FAISS index files (per-meeting)
│   └── raw/                          # Uploaded file storage
│
├── guide/                            # Architecture and documentation
│   ├── DEMO_GUIDE.md                 # Complete demo script
│   ├── context.md                    # Project context and status
│   ├── dfd.txt                       # Data flow diagram
│   └── ARCHITECTURE_VISUAL.txt       # Visual architecture documentation
│
├── deployment/                       # Deployment configurations
│   ├── colab/                        # Google Colab deployment
│   └── huggingface/                  # Hugging Face Spaces deployment
│
├── app.py                            # Streamlit application entry point
├── requirements.txt                  # Python dependencies
├── .env.example                      # Environment variable template
└── README.md                         # This file
```

---

## Performance Characteristics

### Processing Times (Typical)

- **Document Parsing**: < 2 seconds per file (varies by size)
- **Text Chunking**: < 100ms for 10 chunks
- **Embedding Generation**: 
  - CPU: < 1 second per 10 chunks
  - GPU: < 0.2 seconds per 10 chunks
  - Model load: ~5 seconds (first time only)
- **FAISS Indexing**: < 500ms per batch
- **Vector Search**: < 100ms for top-k retrieval
- **LLM Brief Generation**: 5-15 seconds (provider-dependent)
- **Total Pipeline**: 7-20 seconds for typical meeting (2 files)

### Scalability Considerations

- **Per-Meeting Isolation**: FAISS indices are isolated per meeting, enabling horizontal scaling
- **GPU Acceleration**: Automatic GPU detection with CPU fallback for embedding generation
- **Batch Processing**: Embeddings generated in batches (64 on GPU, 16 on CPU)
- **Database Optimization**: SQLite with proper indexing on foreign keys

---

## API Reference

### Core Orchestrator Methods

**CopilotOrchestrator Class** (`agents/copilot_orchestrator.py`)

```python
class CopilotOrchestrator:
    def __init__(provider: str = "gemini")
        """Initialize orchestrator with specified LLM provider."""
    
    def ingest_material(file_bytes: bytes, filename: str, meeting_id: str) -> dict
        """Ingest document: parse, chunk, embed, index."""
    
    def generate_brief(meeting_id: str, title: str, date: str) -> dict
        """Generate meeting brief via multi-agent pipeline."""
    
    def recall_previous_brief(meeting_id: str) -> MeetingBrief
        """Retrieve most recent brief for meeting."""
    
    def answer_question(meeting_id: str, question: str) -> dict
        """Answer question using semantic search + LLM."""
```

### Database Operations

**Database Class** (`core/db.py`)

```python
class Database:
    def create_meeting(title: str, date: str, ...) -> str
        """Create new meeting, returns meeting_id."""
    
    def add_material(meeting_id: str, filename: str, ...) -> str
        """Add material to meeting, returns material_id."""
    
    def save_brief(meeting_id: str, model: str, brief_dict: dict) -> str
        """Persist brief to database, returns brief_id."""
    
    def get_latest_brief(meeting_id: str) -> dict
        """Retrieve most recent brief for meeting."""
```

---

## Development

### Code Standards

- **Type Hints**: All functions include type annotations
- **Docstrings**: Comprehensive docstrings following Google style
- **Error Handling**: Structured logging with error recovery
- **Testing**: Unit tests for core modules (see guide/ for test strategies)

### Logging

The system uses structured logging with consistent prefixes:
- `[INFO]`: Informational messages
- `[OK]`: Successful operations
- `[WARNING]`: Non-critical issues
- `[ERROR]`: Error conditions

Agent-specific logging uses prefixes: `[IngestionTool]`, `[RecallTool]`, `[Synthesis]`, `[MemoryTool]`, `[QA]`

---

## Deployment

### Streamlit Cloud

1. Push repository to GitHub
2. Connect to Streamlit Cloud
3. Configure secrets (API keys)
4. Deploy

### Hugging Face Spaces

See `deployment/huggingface/README.md` for detailed instructions.

### Google Colab

See `deployment/colab/ENHANCED_NOTEBOOK_GUIDE.md` for Colab deployment.

---

## Technical Highlights

### Neural Network Integration
- SentenceTransformer model (all-MiniLM-L6-v2) for semantic embeddings
- 384-dimensional vector representations
- GPU acceleration with automatic CPU fallback
- Batch processing optimization

### Vector Search Implementation
- FAISS IndexFlatIP for cosine similarity search
- Per-meeting index isolation for data privacy
- Top-k retrieval with similarity scoring
- Efficient index persistence and loading

### LLM Integration Patterns
- LangChain abstraction layer for multi-provider support
- Structured output generation with JSON schema validation
- Robust error handling with JSON repair logic
- Cross-meeting memory injection for context continuity

### Data Architecture
- SQLite for structured data with foreign key relationships
- FAISS for vector embeddings with per-meeting namespacing
- Pydantic models for type-safe data validation
- Complete audit trail with timestamps and model tracking

---

## Limitations & Future Enhancements

### Current Limitations
- Single-user architecture (SQLite-based)
- Local vector storage (FAISS indices on filesystem)
- No real-time collaboration features
- Limited to text-based document formats

### Planned Enhancements
- Multi-user support with PostgreSQL backend
- Cloud vector database integration (Pinecone, Weaviate)
- Real-time collaboration features
- Audio/video transcription support
- Calendar integration for automatic meeting detection
- Email integration for material ingestion

---

## License

See LICENSE file for details.

---

## Acknowledgments

Built with:
- LangChain for multi-agent orchestration
- SentenceTransformers for semantic embeddings
- FAISS for vector search
- Streamlit for web interface
- Pydantic for data validation

---

**Status**: Production-ready MVP  
**Version**: 1.0.0  
**Last Updated**: November 2025
