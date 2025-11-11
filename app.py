"""
Executive Intelligence Copilot - Production UI
Modern, premium interface for AI-powered meeting preparation
"""

import streamlit as st
import os
from dotenv import load_dotenv
from datetime import datetime
import json

from core.db import Database
from core.parsing import parse_file, parse_pasted_text
from core.recall import recall_context, format_context_blocks
from core.synth import generate_brief, load_prompt_template
from core.schema import MeetingBrief
from agents.copilot_orchestrator import CopilotOrchestrator

load_dotenv()

st.set_page_config(
    page_title="Executive Intelligence Copilot",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Enhanced custom CSS for premium look
st.markdown("""
    <style>
    /* Global Styles */
    .main {
        padding: 2rem 1rem;
        background: linear-gradient(135deg, #f8f9fa 0%, #ffffff 100%);
    }
    
    /* Typography */
    h1 {
        font-weight: 700;
        letter-spacing: -0.02em;
        background: linear-gradient(135deg, #1a1a1a 0%, #4a4a4a 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
    }
    
    h2, h3 {
        font-weight: 600;
        color: #2c3e50;
    }
    
    /* Card Components */
    .premium-card {
        background: white;
        border-radius: 12px;
        padding: 1.5rem;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
        border: 1px solid #e8e8e8;
        margin-bottom: 1rem;
        transition: all 0.3s ease;
    }
    
    .premium-card:hover {
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.1);
        transform: translateY(-2px);
    }
    
    /* Status Badges */
    .status-badge {
        display: inline-block;
        padding: 0.25rem 0.75rem;
        border-radius: 20px;
        font-size: 0.85rem;
        font-weight: 600;
        margin-right: 0.5rem;
    }
    
    .badge-success {
        background: #d4edda;
        color: #155724;
    }
    
    .badge-warning {
        background: #fff3cd;
        color: #856404;
    }
    
    .badge-info {
        background: #d1ecf1;
        color: #0c5460;
    }
    
    .badge-primary {
        background: #cfe2ff;
        color: #084298;
    }
    
    /* Expander Styling */
    .streamlit-expanderHeader {
        background: white;
        border-radius: 8px;
        border: 1px solid #e8e8e8;
        padding: 0.75rem 1rem;
        font-weight: 600;
    }
    
    .streamlit-expanderHeader:hover {
        background: #f8f9fa;
        border-color: #d0d0d0;
    }
    
    /* Button Enhancements */
    .stButton > button {
        border-radius: 8px;
        font-weight: 600;
        transition: all 0.2s ease;
        border: none;
    }
    
    .stButton > button:hover {
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
    }
    
    /* Sidebar Styling */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #ffffff 0%, #f8f9fa 100%);
    }
    
    [data-testid="stSidebar"] .block-container {
        padding-top: 2rem;
    }
    
    /* Input Fields */
    .stTextInput > div > div > input,
    .stTextArea > div > div > textarea {
        border-radius: 8px;
        border: 1px solid #d0d0d0;
    }
    
    .stTextInput > div > div > input:focus,
    .stTextArea > div > div > textarea:focus {
        border-color: #4a90e2;
        box-shadow: 0 0 0 1px #4a90e2;
    }
    
    /* Data Tables */
    .dataframe {
        border-radius: 8px;
        overflow: hidden;
        border: 1px solid #e8e8e8;
    }
    
    /* Info/Warning/Success Messages */
    .stAlert {
        border-radius: 8px;
        border-left: 4px solid;
    }
    
    /* Progress Bar */
    .stProgress > div > div {
        border-radius: 8px;
    }
    
    /* Dividers */
    hr {
        margin: 2rem 0;
        border: none;
        height: 1px;
        background: linear-gradient(90deg, transparent, #e8e8e8, transparent);
    }
    </style>
""", unsafe_allow_html=True)

# Initialize database (cached to avoid re-initialization on rerun)
@st.cache_resource
def init_database():
    """Initialize and return database connection."""
    return Database()

@st.cache_resource(show_spinner="Loading AI models...")
def init_orchestrator():
    """Initialize orchestrator with configured provider."""
    provider = os.getenv("LLM_PROVIDER", "gemini")
    return CopilotOrchestrator(provider=provider)

@st.cache_resource(show_spinner="Loading embedding model...")
def preload_embedding_model():
    """Preload the embedding model to cache it."""
    from core.embed import get_model, get_device
    device = get_device()
    model = get_model()
    return {"device": device, "model_loaded": True}


def convert_brief_to_markdown(brief: MeetingBrief) -> str:
    """Convert a MeetingBrief to Markdown format."""
    
    md = "# Meeting Brief\n\n"
    md += "_Generated: {}_\n\n".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    md += "---\n\n"
    
    md += "## Last Meeting Recap\n\n"
    md += "{}\n\n".format(brief.last_meeting_recap)
    
    md += "## Open Action Items\n\n"
    if brief.open_action_items:
        for item in brief.open_action_items:
            status_emoji = "✅" if item.status == "done" else "🔴" if item.status == "blocked" else "🔵"
            md += "- {} **{}**\n".format(status_emoji, item.item)
            md += "  - Owner: {}\n".format(item.owner)
            md += "  - Due: {}\n".format(item.due or "Not set")
            md += "  - Status: {}\n\n".format(item.status)
    else:
        md += "_No action items found_\n\n"
    
    md += "## Key Topics Today\n\n"
    if brief.key_topics_today:
        for i, topic in enumerate(brief.key_topics_today, 1):
            md += "{}. {}\n".format(i, topic)
        md += "\n"
    else:
        md += "_No topics identified_\n\n"
    
    md += "## Proposed Agenda\n\n"
    if brief.proposed_agenda:
        total_minutes = sum([item.minutes for item in brief.proposed_agenda])
        for i, agenda_item in enumerate(brief.proposed_agenda, 1):
            md += "{}. **{}** ({} min)\n".format(i, agenda_item.topic, agenda_item.minutes)
            if agenda_item.owner:
                md += "   - Owner: {}\n".format(agenda_item.owner)
        md += "\n_Total duration: {} minutes_\n\n".format(total_minutes)
    else:
        md += "_No agenda items found_\n\n"
    
    md += "## Evidence & Sources\n\n"
    if brief.evidence:
        for i, evidence in enumerate(brief.evidence, 1):
            md += "### Source [{}]: {}\n\n".format(i, evidence.source)
            md += "```\n{}\n```\n\n".format(evidence.snippet)
    else:
        md += "_No evidence found_\n\n"
    
    return md


def render_qa_section():
    """Render the Q&A interface with enhanced styling."""
    
    db = init_database()
    
    st.divider()
    
    st.markdown('<h2 style="margin-bottom: 0.5rem;">💬 Interactive Q&A</h2>', unsafe_allow_html=True)
    st.caption("Ask questions about your meeting materials and get AI-powered answers")
    
    if not st.session_state.current_meeting_id:
        st.info("👈 Select a meeting first to start asking questions")
        return
    
    materials = db.get_materials(st.session_state.current_meeting_id)
    if not materials:
        st.info("📎 Upload materials first to enable intelligent Q&A")
        return
    
    # Question input with better layout
    st.markdown("---")
    col1, col2 = st.columns([5, 1])
    
    with col1:
        question = st.text_input(
            "Your Question",
            placeholder="What are the key risks mentioned? Who owns the Q4 deliverables? What's the budget allocation?",
            key="qa_question_input",
            label_visibility="collapsed"
        )
    
    with col2:
        ask_button = st.button("🔍 Ask", use_container_width=True, type="primary")
    
    if ask_button:
        if not question.strip():
            st.warning("Please enter a question")
        else:
            try:
                with st.spinner("🤔 Analyzing documents and generating answer..."):
                    orchestrator = init_orchestrator()
                    
                    result = orchestrator.answer_question(
                        meeting_id=st.session_state.current_meeting_id,
                        question=question
                    )
                    
                    if result.get("success"):
                        st.session_state.qa_history.append({
                            "question": question,
                            "answer": result["answer"],
                            "sources": result["sources"],
                            "timestamp": datetime.now().strftime("%H:%M:%S")
                        })
                        st.rerun()
                    else:
                        st.error("Error: {}".format(result.get("error", "Unknown error")))
            
            except Exception as e:
                st.error("Error answering question: {}".format(str(e)))
    
    # Display conversation history with improved styling
    if st.session_state.qa_history:
        st.markdown("---")
        st.markdown('<h3 style="margin-top: 1.5rem;">📚 Conversation History</h3>', unsafe_allow_html=True)
        
        for i, qa in enumerate(reversed(st.session_state.qa_history)):
            with st.expander("**{}** • {}".format(qa["question"], qa.get("timestamp", "")), expanded=(i == 0)):
                st.markdown("**Answer:**")
                st.markdown('<div class="premium-card">{}</div>'.format(qa["answer"]), unsafe_allow_html=True)
                
                if qa.get("sources"):
                    st.markdown("**Referenced Sources:**")
                    for source in qa["sources"]:
                        st.markdown('<span class="status-badge badge-info">📄 {}</span>'.format(source), unsafe_allow_html=True)


def render_brief(brief: MeetingBrief):
    """Render a MeetingBrief object with premium styling."""
    
    # Last Meeting Recap
    with st.expander("📋 Last Meeting Recap", expanded=True):
        st.markdown('<div class="premium-card">{}</div>'.format(brief.last_meeting_recap), unsafe_allow_html=True)
    
    # Open Action Items with status badges
    with st.expander("✅ Open Action Items", expanded=True):
        if brief.open_action_items:
            for item in brief.open_action_items:
                # Status-based styling
                if item.status == "done":
                    badge_class = "badge-success"
                    status_icon = "✅"
                elif item.status == "blocked":
                    badge_class = "badge-warning"
                    status_icon = "🔴"
                else:
                    badge_class = "badge-info"
                    status_icon = "🔵"
                
                st.markdown(
                    '<div class="premium-card">'
                    '{} <strong>{}</strong>'
                    '<br><small>👤 {} • 📅 {} • <span class="status-badge {}">{}</span></small>'
                    '</div>'.format(
                        status_icon, 
                        item.item,
                        item.owner,
                        item.due or "No deadline",
                        badge_class,
                        item.status.upper()
                    ),
                    unsafe_allow_html=True
                )
        else:
            st.info("No action items found")
    
    # Key Topics
    with st.expander("🎯 Key Topics for Discussion", expanded=True):
        if brief.key_topics_today:
            topics_html = '<div class="premium-card"><ol style="margin: 0; padding-left: 1.5rem;">'
            for topic in brief.key_topics_today:
                topics_html += '<li style="margin-bottom: 0.5rem;"><strong>{}</strong></li>'.format(topic)
            topics_html += '</ol></div>'
            st.markdown(topics_html, unsafe_allow_html=True)
        else:
            st.info("No topics identified")
    
    # Proposed Agenda
    with st.expander("📅 Proposed Agenda", expanded=True):
        if brief.proposed_agenda:
            total_minutes = sum([item.minutes for item in brief.proposed_agenda])
            
            for i, agenda_item in enumerate(brief.proposed_agenda, 1):
                owner_text = " • Owner: {}".format(agenda_item.owner) if agenda_item.owner else ""
                st.markdown(
                    '<div class="premium-card">'
                    '<strong>{}. {}</strong> '
                    '<span class="status-badge badge-primary">⏱ {} min</span>'
                    '<br><small>{}</small>'
                    '</div>'.format(
                        i,
                        agenda_item.topic,
                        agenda_item.minutes,
                        owner_text if owner_text else "No owner assigned"
                    ),
                    unsafe_allow_html=True
                )
            
            st.markdown(
                '<div style="text-align: right; margin-top: 1rem;">'
                '<span class="status-badge badge-info">📊 Total Duration: {} minutes</span>'
                '</div>'.format(total_minutes),
                unsafe_allow_html=True
            )
        else:
            st.info("No agenda items found")
    
    # Evidence & Sources
    with st.expander("📌 Evidence & Sources", expanded=False):
        if brief.evidence:
            for i, evidence in enumerate(brief.evidence, 1):
                st.markdown(
                    '<div class="premium-card">'
                    '<strong>Source [{}]:</strong> {}'
                    '<pre style="background: #f8f9fa; padding: 1rem; border-radius: 6px; margin-top: 0.5rem; white-space: pre-wrap;">{}</pre>'
                    '</div>'.format(i, evidence.source, evidence.snippet),
                    unsafe_allow_html=True
                )
        else:
            st.info("No evidence found")

def main():
    """Main Streamlit application with premium UI."""
    
    db = init_database()
    model_info = preload_embedding_model()
    
    # Initialize session state
    if "current_meeting_id" not in st.session_state:
        st.session_state.current_meeting_id = None
    if "materials_added" not in st.session_state:
        st.session_state.materials_added = []
    if "generated_brief" not in st.session_state:
        st.session_state.generated_brief = None
    if "brief_meeting_id" not in st.session_state:
        st.session_state.brief_meeting_id = None
    if "show_download_options" not in st.session_state:
        st.session_state.show_download_options = False
    if "qa_history" not in st.session_state:
        st.session_state.qa_history = []
    
    # Header section with gradient and better layout
    col_title, col_status = st.columns([4, 1])
    
    with col_title:
        st.title("🧠 Executive Intelligence Copilot")
        st.markdown('<p style="font-size: 1.1rem; color: #6c757d; margin-top: -1rem;">AI-powered meeting preparation in minutes</p>', unsafe_allow_html=True)
    
    with col_status:
        device_badge_class = "badge-success" if model_info["device"] == "cuda" else "badge-info"
        device_text = "⚡ GPU" if model_info["device"] == "cuda" else "💻 CPU"
        st.markdown(
            '<div style="text-align: right; margin-top: 1.5rem;">'
            '<span class="status-badge {}">{}</span>'
            '</div>'.format(device_badge_class, device_text),
            unsafe_allow_html=True
        )
    
    # Demo mode notification
    if os.path.exists("/tmp"):
        st.info("ℹ️ **Demo Mode**: Running with temporary storage. Data persists during session only.")
    
    # Enhanced Sidebar
    with st.sidebar:
        st.markdown('<h2 style="margin-bottom: 0.5rem;">⚙️ Control Panel</h2>', unsafe_allow_html=True)
        st.caption("Manage your meetings and materials")
        st.markdown("---")
        
        # Meeting Selection Section
        st.markdown("### 📅 Meeting")
        meeting_action = st.radio(
            "Choose action",
            ["Create New Meeting", "Select Existing Meeting"],
            label_visibility="collapsed"
        )
        
        if meeting_action == "Create New Meeting":
            st.markdown('<div style="background: #f8f9fa; padding: 1rem; border-radius: 8px; margin-top: 0.5rem;">', unsafe_allow_html=True)
            meeting_title = st.text_input("Meeting Title", placeholder="e.g., Q4 Strategy Review")
            meeting_date = st.date_input("Meeting Date")
            attendees = st.text_input("Attendees", placeholder="John, Jane, Bob")
            tags = st.text_input("Tags", placeholder="strategy, planning")
            
            if st.button("✅ Create Meeting", use_container_width=True, type="primary"):
                if meeting_title:
                    date_str = meeting_date.strftime("%Y-%m-%d") if meeting_date else None
                    
                    meeting_id = db.create_meeting(
                        title=meeting_title,
                        date=date_str,
                        attendees=attendees if attendees else None,
                        tags=tags if tags else None
                    )
                    
                    st.session_state.current_meeting_id = meeting_id
                    st.session_state.generated_brief = None
                    st.session_state.brief_meeting_id = None
                    st.session_state.qa_history = []
                    
                    st.success("✅ Meeting created successfully!")
                    st.rerun()
                else:
                    st.error("Please enter a meeting title")
            
            st.markdown('</div>', unsafe_allow_html=True)
        
        else:
            meetings = db.list_meetings()
            
            if meetings:
                meeting_options = ["{} ({})".format(m['title'], m['date'] or 'No date') for m in meetings]
                meeting_ids = [m['id'] for m in meetings]
                
                selected_index = st.selectbox(
                    "Choose a meeting",
                    range(len(meeting_options)),
                    format_func=lambda x: meeting_options[x]
                )
                
                if selected_index is not None:
                    selected_meeting_id = meeting_ids[selected_index]
                    
                    # Only clear brief if meeting has changed
                    if st.session_state.current_meeting_id != selected_meeting_id:
                        st.session_state.current_meeting_id = selected_meeting_id
                        st.session_state.generated_brief = None
                        st.session_state.brief_meeting_id = None
                        st.session_state.qa_history = []
                    
                    selected_meeting = meetings[selected_index]
                    st.markdown(
                        '<div style="background: #e8f4f8; padding: 1rem; border-radius: 8px; margin-top: 0.5rem;">'
                        '<small><strong>Selected:</strong> {}<br>'
                        '<strong>Date:</strong> {}<br>'
                        '<strong>Created:</strong> {}</small>'
                        '</div>'.format(
                            selected_meeting['title'],
                            selected_meeting['date'] or 'Not set',
                            selected_meeting['created_at'][:10]
                        ),
                        unsafe_allow_html=True
                    )
            else:
                st.info("No meetings found. Create one above!")
                st.session_state.current_meeting_id = None
        
        st.markdown("---")
        
        # Materials Section
        st.markdown("### 📎 Materials")
        
        if st.session_state.current_meeting_id is None:
            st.warning("Select a meeting first")
        else:
            material_source = st.radio(
                "Add materials via",
                ["Upload Files", "Paste Text"],
                label_visibility="collapsed"
            )
            
            if material_source == "Upload Files":
                uploaded_files = st.file_uploader(
                    "Upload documents",
                    type=["pdf", "docx", "pptx", "txt"],
                    accept_multiple_files=True,
                    help="Supported: PDF, DOCX, PPTX, TXT"
                )
                
                if uploaded_files and st.button("📤 Upload Files", use_container_width=True, type="primary"):
                    meeting_id = st.session_state.current_meeting_id
                    success_count = 0
                    error_count = 0
                    
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    for idx, uploaded_file in enumerate(uploaded_files):
                        try:
                            progress = (idx + 1) / len(uploaded_files)
                            progress_bar.progress(progress)
                            status_text.text("Processing {}...".format(uploaded_file.name))
                            
                            file_bytes = uploaded_file.read()
                            text, media_type = parse_file(file_bytes, uploaded_file.name)
                            
                            if text:
                                material_id = db.add_material(
                                    meeting_id=meeting_id,
                                    filename=uploaded_file.name,
                                    media_type=media_type,
                                    text=text
                                )
                                success_count += 1
                            else:
                                error_count += 1
                        except Exception as e:
                            error_count += 1
                            st.error("Error: {}".format(str(e)))
                    
                    progress_bar.empty()
                    status_text.empty()
                    
                    if success_count > 0:
                        st.session_state.generated_brief = None
                        st.session_state.qa_history = []
                        st.success("✅ Uploaded {} file(s)".format(success_count))
                        st.balloons()
                        st.rerun()
            
            else:
                pasted_text = st.text_area(
                    "Paste text content",
                    height=150,
                    placeholder="Paste meeting notes, emails, or documents here...",
                    help="Paste any text content you want to analyze"
                )
                
                if pasted_text and st.button("📝 Save Text", use_container_width=True, type="primary"):
                    meeting_id = st.session_state.current_meeting_id
                    text, media_type = parse_pasted_text(pasted_text)
                    
                    if text:
                        material_id = db.add_material(
                            meeting_id=meeting_id,
                            filename="pasted_text.txt",
                            media_type=media_type,
                            text=text
                        )
                        st.success("✅ Saved ({:,} chars)".format(len(text)))
                        st.session_state.generated_brief = None
                        st.session_state.qa_history = []
                        st.balloons()
                        st.rerun()
                    else:
                        st.warning("No text to save")
        
        st.markdown("---")
        
        # Actions Section
        st.markdown("### ⚡ Actions")
        
        # Reset button for clearing current view
        if st.button("🔄 Clear Current View", use_container_width=True, help="Clear displayed brief and Q&A history"):
            st.session_state.generated_brief = None
            st.session_state.brief_meeting_id = None
            st.session_state.qa_history = []
            st.success("✅ View cleared")
            st.rerun()
        
        # Primary action button
        if st.button("🎯 Generate Brief", use_container_width=True, type="primary"):
            if not st.session_state.current_meeting_id:
                st.warning("Select a meeting first")
            else:
                materials = db.get_materials(st.session_state.current_meeting_id)
                if not materials:
                    st.warning("Upload materials first")
                else:
                    try:
                        with st.spinner("🧠 Generating intelligent brief..."):
                            orchestrator = init_orchestrator()
                            current_meeting = db.get_meeting(st.session_state.current_meeting_id)
                            
                            result = orchestrator.generate_brief(
                                meeting_id=st.session_state.current_meeting_id,
                                title=current_meeting['title'],
                                date=current_meeting['date'] or "Today"
                            )
                            
                            if result.get("success"):
                                st.session_state.generated_brief = result["brief"]
                                st.session_state.brief_meeting_id = st.session_state.current_meeting_id
                                provider = result.get("provider", "unknown")
                                st.success("✅ Brief ready • {}".format(provider.upper()))
                                st.rerun()
                            else:
                                st.error("Error: {}".format(result.get("error", "Unknown error")))
                    
                    except Exception as e:
                        st.error("Error: {}".format(str(e)))
        
        # Secondary actions
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("🔍 Recall Previous", use_container_width=True):
                if st.session_state.current_meeting_id:
                    try:
                        orchestrator = init_orchestrator()
                        previous_brief = orchestrator.recall_previous_brief(
                            st.session_state.current_meeting_id
                        )
                        if previous_brief:
                            st.session_state.generated_brief = previous_brief
                            st.session_state.brief_meeting_id = st.session_state.current_meeting_id
                            st.success("✅ Brief loaded")
                            st.rerun()
                        else:
                            st.info("No previous brief found")
                    except Exception as e:
                        st.error("Error: {}".format(str(e)))
                else:
                    st.warning("Select a meeting first")
        
        with col2:
            if st.button("💾 Download", use_container_width=True):
                if st.session_state.generated_brief:
                    st.session_state.show_download_options = True
                else:
                    st.warning("Generate brief first")
        
        # Download options
        if st.session_state.get("show_download_options", False) and st.session_state.generated_brief:
            st.markdown("---")
            st.markdown("**📥 Export Options**")
            
            brief_dict = st.session_state.generated_brief.model_dump()
            json_str = json.dumps(brief_dict, indent=2)
            markdown_content = convert_brief_to_markdown(st.session_state.generated_brief)
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.download_button(
                    label="📄 JSON",
                    data=json_str,
                    file_name="brief_{}.json".format(datetime.now().strftime("%Y%m%d_%H%M%S")),
                    mime="application/json",
                    use_container_width=True
                )
            
            with col2:
                st.download_button(
                    label="📝 Markdown",
                    data=markdown_content,
                    file_name="brief_{}.md".format(datetime.now().strftime("%Y%m%d_%H%M%S")),
                    mime="text/markdown",
                    use_container_width=True
                )
            
            if st.button("✕ Close", use_container_width=True):
                st.session_state.show_download_options = False
                st.rerun()
        
        # Brief History
        if st.session_state.current_meeting_id:
            brief_history = db.get_brief_history(st.session_state.current_meeting_id)
            
            if brief_history and len(brief_history) > 1:
                st.markdown("---")
                st.markdown("### 📚 History")
                
                history_options = [
                    "{} • {}".format(
                        b['created_at'][:16], 
                        b['model'].upper()
                    ) 
                    for b in brief_history
                ]
                
                selected_brief_idx = st.selectbox(
                    "Previous versions",
                    range(len(history_options)),
                    format_func=lambda x: history_options[x]
                )
                
                if st.button("📖 Load", use_container_width=True):
                    try:
                        selected_brief_id = brief_history[selected_brief_idx]['id']
                        brief_data = db.get_brief_by_id(selected_brief_id)
                        
                        if brief_data:
                            st.session_state.generated_brief = MeetingBrief(**brief_data["brief"])
                            st.session_state.brief_meeting_id = st.session_state.current_meeting_id
                            st.success("✅ Loaded")
                            st.rerun()
                    except Exception as e:
                        st.error("Error: {}".format(str(e)))
    
    # Main content area
    st.markdown("---")
    
    # Current meeting status card
    if st.session_state.current_meeting_id:
        current_meeting = db.get_meeting(st.session_state.current_meeting_id)
        if current_meeting:
            materials = db.get_materials(st.session_state.current_meeting_id)
            materials_count = len(materials) if materials else 0
            
            st.markdown(
                '<div class="premium-card" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white;">'
                '<h3 style="margin: 0; color: white;">📅 {}</h3>'
                '<p style="margin: 0.5rem 0 0 0; opacity: 0.9;">'
                '📆 {} • 📎 {} material(s) • {} brief'
                '</p>'
                '</div>'.format(
                    current_meeting['title'],
                    current_meeting['date'] or 'No date set',
                    materials_count,
                    "✅ Generated" if st.session_state.generated_brief else "⏳ Pending"
                ),
                unsafe_allow_html=True
            )
    else:
        st.markdown(
            '<div class="premium-card" style="background: #f8f9fa; text-align: center; padding: 3rem;">'
            '<h3 style="color: #6c757d;">👈 Get Started</h3>'
            '<p style="color: #6c757d;">Create or select a meeting in the sidebar to begin</p>'
            '</div>',
            unsafe_allow_html=True
        )
    
    # Display generated brief (with safety check to ensure brief matches current meeting)
    if (st.session_state.generated_brief and 
        st.session_state.brief_meeting_id == st.session_state.current_meeting_id):
        st.markdown('<h2 style="margin-top: 2rem;">📊 Meeting Brief</h2>', unsafe_allow_html=True)
        st.markdown('<div class="status-badge badge-success">✓ Generated</div>', unsafe_allow_html=True)
        st.markdown("---")
        render_brief(st.session_state.generated_brief)
    elif st.session_state.current_meeting_id:
        st.markdown('<h2 style="margin-top: 2rem;">📊 Meeting Brief</h2>', unsafe_allow_html=True)
        st.markdown(
            '<div class="premium-card" style="text-align: center; padding: 3rem; background: #f8f9fa;">'
            '<h3 style="color: #6c757d;">No Brief Generated Yet</h3>'
            '<p style="color: #6c757d;">Add materials and click "Generate Brief" in the sidebar</p>'
            '</div>',
            unsafe_allow_html=True
        )
    
    # Q&A Section
    if st.session_state.current_meeting_id:
        render_qa_section()
    
    # Materials section
    if st.session_state.current_meeting_id:
        st.markdown("---")
        st.markdown('<h2 style="margin-top: 2rem;">📁 Materials Library</h2>', unsafe_allow_html=True)
        
        materials = db.get_materials(st.session_state.current_meeting_id)
        
        if materials:
            import pandas as pd
            
            display_data = []
            for mat in materials:
                display_data.append({
                    "📄 File": mat['filename'],
                    "Type": mat['media_type'].upper(),
                    "Size": "{:,} chars".format(mat['char_count']),
                    "Added": mat['created_at'][:16]
                })
            
            df = pd.DataFrame(display_data)
            st.dataframe(df, use_container_width=True, hide_index=True)
            
            total_chars = sum([m['char_count'] for m in materials])
            st.markdown(
                '<div style="text-align: right; margin-top: 0.5rem;">'
                '<span class="status-badge badge-info">📊 {} material(s) • {:,} total characters</span>'
                '</div>'.format(len(materials), total_chars),
                unsafe_allow_html=True
            )
        else:
            st.markdown(
                '<div class="premium-card" style="text-align: center; padding: 2rem; background: #f8f9fa;">'
                '<p style="color: #6c757d;">No materials yet • Add files or text in the sidebar</p>'
                '</div>',
                unsafe_allow_html=True
            )
    
    # Footer
    st.markdown("---")
    st.markdown(
        '<div style="text-align: center; padding: 2rem 0; color: #6c757d;">'
        '<p style="margin: 0; font-size: 0.9rem;">Executive Intelligence Copilot</p>'
        '<p style="margin: 0.5rem 0 0 0; font-size: 0.8rem;">Powered by AI • Built for Executives</p>'
        '</div>',
        unsafe_allow_html=True
    )


if __name__ == "__main__":
    main()
