# intelligence_copilot
An AI assistant that automatically prepares senior leaders for their meetings by summarizing recent conversations, documents, and decisions — reducing information overload and saving time spent on pre-meeting review.

🤖 Executive Intelligence Copilot

An AI assistant that automatically prepares senior leaders for meetings by summarizing recent conversations, documents, decisions, and action items — reducing information overload and saving valuable preparation time.

👉 Live Demo: https://intelligence-copilot.vercel.app

This project was built as part of an applied AI systems initiative, integrating LLM reasoning, semantic retrieval, and structured synthesis into a clean Streamlit dashboard for executive meeting preparation.

🎯 Project Overview

The Executive Intelligence Copilot helps leaders walk into any meeting fully prepared by transforming scattered materials — such as documents, transcripts, and notes — into a single, structured briefing.

The system brings together:

AI-generated meeting briefs

Automatic extraction of key topics and action items

Proposed meeting agendas

Semantic search and interactive Q&A

Versioned brief histories

Export options for easy sharing

This turns the manual, time-consuming process of meeting prep into a streamlined, intelligent workflow.

🧠 Key Features
🔹 Automated Meeting Brief Generation

For any meeting, the copilot generates a structured brief containing:

Last Meeting Recap

Open Action Items (with owners, due dates, statuses)

Key Topics for Today

Proposed Agenda

Evidence & Source Snippets from uploaded content

Everything is displayed in expandable, easy-to-read sections.

🔹 Multi-Source Document Ingestion

Upload or paste:

PDFs

Word documents

PowerPoint slides

Text files

Raw notes or emails

All materials are parsed, embedded, indexed in FAISS, and stored in SQLite for persistent retrieval.

🔹 Interactive Q&A

Ask questions like:

“What decisions were made last meeting?”

“Who is responsible for the marketing deliverables?”

“Summarize all risks identified this month.”

The system retrieves relevant content, queries the LLM, and returns grounded, source-backed answers.

🔹 Brief History & Versioning

Each generated brief is saved with a timestamp and model information.
You can easily view or reload previous versions through the History panel.

🔹 Export as JSON or Markdown

All briefs can be exported for use in:

Notion

Google Docs

Confluence

Internal knowledge bases

🏗️ System Architecture

The copilot is built on a modular retrieval-augmented generation (RAG) architecture:

Streamlit UI for meetings, materials, briefs, and Q&A

SQLModel + SQLite for meeting, brief, and document storage

Sentence Transformers for text embeddings

FAISS for semantic vector search

Copilot Orchestrator to coordinate retrieval, synthesis, and Q&A

LLM Providers (Gemini / OpenAI / Anthropic) for generation and reasoning

This design ensures scalability, adaptability, and clear separation of responsibilities.

🧰 Tools and Techniques

Frameworks: Streamlit, SQLModel, LangChain

Models: Sentence Transformers (MiniLM), FAISS for similarity search

LLMs: Gemini / OpenAI / Anthropic (configurable)

File Handling: PyPDF, python-docx, python-pptx

Data Models: Pydantic v2 for typed structured outputs

📘 Workflow Summary
Step 1 — Create a Meeting

Add title, date, attendees, and tags.

Step 2 — Add Materials

Upload files or paste text. Everything is parsed and indexed.

Step 3 — Generate the Brief

The orchestrator retrieves relevant content and synthesizes a structured brief.

Step 4 — Ask Follow-Up Questions

Use the Q&A section to pull insights from all meeting materials.

Step 5 — Review History or Export

Reload earlier versions or download the brief as Markdown or JSON.

🔧 Installation

Clone the repo:

git clone https://github.com/sdv1708/intelligence_copilot.git


Install dependencies:

pip install -r requirements.txt


Set up .env using env.example (API keys for provider of choice)

Run the app:

streamlit run app.py

🛣️ Future Enhancements

Auto-creating meetings from calendar invites

Integrations with Slack, Gmail, and document repositories

Real-time meeting assistant (transcription + note generation)

Organization-wide deployment with user accounts

Advanced analytics (topic trends, workload distribution, etc.)

👤 Maintainer

Abimanyu Vijay
MSBA — University of Maryland
AI Systems & Decision Intelligence Enthusiast

📜 License

This project is open-sourced under the MIT License.
