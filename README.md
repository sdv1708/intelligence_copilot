# Executive Intelligence Copilot

An AI assistant that automatically prepares senior leaders for their meetings by summarizing recent conversations, documents, decisions, and action items. The goal is to reduce information overload and save time spent on pre-meeting preparation.

---

## Project Overview

The Executive Intelligence Copilot transforms scattered meeting materials into a single, structured briefing that leaders can review in minutes.  
The system integrates retrieval-augmented generation, structured synthesis, and semantic search to help users quickly understand key updates before any meeting.

Key capabilities include:

- AI-generated meeting briefs  
- Automatic extraction of action items and key topics  
- Proposed meeting agendas  
- Interactive Q&A over all stored materials  
- Versioned brief histories  
- Export options (JSON and Markdown)  

---

## Features

### Automated Meeting Briefs

For each meeting, the copilot generates a structured brief containing:

- Last meeting recap  
- Open action items (owners, due dates, status)  
- Key topics for discussion  
- Proposed agenda (topics, owners, time estimates)  
- Evidence and source snippets from uploaded materials  

### Multi-Source Material Ingestion

Upload or paste:

- PDFs  
- Word documents  
- PowerPoint files  
- Text files  
- Raw notes, emails, transcripts  

All materials are:

1. Parsed to extract text  
2. Embedded using Sentence Transformers  
3. Indexed using FAISS  
4. Persistently stored via SQLModel (SQLite)  

### Interactive Q&A

Ask natural questions such as:

- “What decisions were made last meeting?”  
- “Who owns the Q4 deliverables?”  
- “Summarize the marketing risks mentioned this month.”  

The system retrieves relevant content and produces grounded, source-linked answers.

### Brief History and Versioning

Each brief is stored with a timestamp and model information.  
Users can reload previous versions from the History panel.

### Export Options

All briefs can be exported as:

- JSON  
- Markdown  

---

## System Architecture

The copilot uses a modular RAG (Retrieval-Augmented Generation) architecture:

- Streamlit UI for meetings, materials, briefs, and Q&A  
- SQLModel + SQLite for persistent storage  
- Sentence Transformers for embeddings  
- FAISS for semantic similarity search  
- A Copilot Orchestrator that coordinates retrieval, synthesis, and Q&A  
- Pluggable LLM providers (Gemini, OpenAI, Anthropic)  

Core directories:

```text
core/        Embeddings, parsing, DB, retrieval, synthesis
agents/      CopilotOrchestrator logic
prompts/     Prompt templates for briefs and Q&A
sample_data/ Example materials
app.py       Main Streamlit application

```
## Tools and Techniques

- Streamlit  
- Sentence Transformers  
- FAISS  
- SQLModel + SQLite  
- LangChain (LLM orchestration)  
- Pydantic v2 models  
- PyPDF, python-docx, python-pptx  

---

## Workflow Summary

### Step 1: Create a Meeting
Add a title, date, attendees, and tags.

### Step 2: Add Materials
Upload files or paste text.  
All content is parsed, embedded, and indexed.

### Step 3: Generate the Brief
The orchestrator retrieves the most relevant information and creates a structured brief.

### Step 4: Ask Questions
Use the Q&A section to ask questions about the stored materials.

### Step 5: Review or Export
Reload previous versions or export the brief as Markdown or JSON.

---

## Installation

### 1. Clone the repository
git clone https://github.com/sdv1708/intelligence_copilot.git

### 2. Install dependencies
pip install -r requirements.txt

### 3. Configure environment variables
Create a `.env` file based on `env.example` and add your LLM API keys.

### 4. Run the application
streamlit run app.py

---

## Future Enhancements

- Calendar integration for automatic meeting creation  
- Slack, Teams, and Gmail ingestion  
- Google Drive and SharePoint connectors  
- Real-time meeting transcription and note generation  
- Organizational multi-user deployment  
- Analytics to identify trends across meetings  

---

## Contributors

- Sanjay Dari Veerabasappa  
- Abimanyu Vijay
- Rohan Vasudevan
- Shilpitha Shetty

---

## License

This project is licensed under the MIT License.
