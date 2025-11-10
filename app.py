"""Streamlit UI for Executive Intelligence Copilot - Day 3 Implementation (LLM Integration)."""

import streamlit as st
import os
from dotenv import load_dotenv
from datetime import datetime
import json

# Import our core modules
from core.db import Database
from core.parsing import parse_file, parse_pasted_text
from core.recall import recall_context, format_context_blocks
from core.synth import generate_brief, load_prompt_template
from core.schema import MeetingBrief

from agents.copilot_orchestrator import CopilotOrchestrator

# Load environment variables
load_dotenv()

# Set page config
st.set_page_config(
    page_title="Executive Intelligence Copilot",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better styling
st.markdown("""
    <style>
    .main {
        padding-top: 2rem;
    }
    .stExpander {
        border: 1px solid #e0e0e0;
        border-radius: 5px;
    }
    </style>
""", unsafe_allow_html=True)

# Initialize database (cached to avoid re-initialization on rerun)
@st.cache_resource
def init_database():
    """Initialize and return database connection."""
    return Database()

@st.cache_resource
def init_orchestrator():
    """Initialize orchestrator with configured provider."""
    provider = os.getenv("LLM_PROVIDER", "gemini")
    return CopilotOrchestrator(provider=provider)


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
    """Render the Q&A interface below the brief."""
    
    db = init_database()
    
    st.divider()
    st.subheader("💬 Ask Questions About Your Documents")
    
    # Check if meeting is selected
    if not st.session_state.current_meeting_id:
        st.info("👈 Select a meeting first to ask questions")
        return
    
    # Check if materials exist
    materials = db.get_materials(st.session_state.current_meeting_id)
    if not materials:
        st.info("📎 Upload materials first to enable Q&A")
        return
    
    # Question input
    col1, col2 = st.columns([4, 1])
    with col1:
        question = st.text_input(
            "Ask a question about your documents:",
            placeholder="e.g., What are the top risks? Who owns the hiring plan? What budget was approved?",
            key="qa_question_input"
        )
    
    with col2:
        ask_button = st.button("💬 Ask", use_container_width=True)
    
    # Handle question submission
    if ask_button:
        if not question.strip():
            st.warning("Please enter a question")
        else:
            try:
                with st.spinner("Searching documents and generating answer..."):
                    orchestrator = init_orchestrator()
                    
                    result = orchestrator.answer_question(
                        meeting_id=st.session_state.current_meeting_id,
                        question=question
                    )
                    
                    if result.get("success"):
                        st.session_state.qa_history.append({
                            "question": question,
                            "answer": result["answer"],
                            "sources": result["sources"]
                        })
                        st.rerun()
                    else:
                        st.error("Error: {}".format(result.get("error", "Unknown error")))
            
            except Exception as e:
                st.error("Error answering question: {}".format(str(e)))
    
    # Display Q&A history
    if st.session_state.qa_history:
        st.subheader("📚 Conversation History")
        
        for i, qa in enumerate(reversed(st.session_state.qa_history)):
            with st.expander("**Q:** {}".format(qa["question"]), expanded=(i == 0)):
                st.write("**Answer:**")
                st.info(qa["answer"])
                
                if qa["sources"]:
                    st.write("**Sources:**")
                    for source in qa["sources"]:
                        st.caption("📄 {}".format(source))


def render_brief(brief: MeetingBrief):
    """Render a MeetingBrief object in the UI."""
    
    # Recap tab
    with st.expander("📋 Last Meeting Recap", expanded=True):
        st.write(brief.last_meeting_recap)
    
    # Open action items tab
    with st.expander("✅ Open Action Items", expanded=True):
        if brief.open_action_items:
            for item in brief.open_action_items:
                status_icon = "✅" if item.status == "done" else "🔴" if item.status == "blocked" else "🔵"
                st.write(f"{status_icon} **{item.item}**")
                st.caption(f"Owner: {item.owner} | Due: {item.due or 'Not set'} | Status: {item.status}")
        else:
            st.info("No action items found")
    
    # Key topics tab
    with st.expander("🎯 Key Topics Today", expanded=True):
        if brief.key_topics_today:
            for i, topic in enumerate(brief.key_topics_today, 1):
                st.write(f"{i}. {topic}")
        else:
            st.info("No topics identified")
    
    # Agenda tab
    with st.expander("📅 Proposed Agenda", expanded=True):
        if brief.proposed_agenda:
            total_minutes = sum([item.minutes for item in brief.proposed_agenda])
            for i, agenda_item in enumerate(brief.proposed_agenda, 1):
                st.write(f"**{i}. {agenda_item.topic}** ({agenda_item.minutes} min)")
                if agenda_item.owner:
                    st.caption(f"Owner: {agenda_item.owner}")
            st.caption(f"Total duration: {total_minutes} minutes")
        else:
            st.info("No agenda items found")
    
    # Evidence tab
    with st.expander("📌 Evidence & Sources", expanded=False):
        if brief.evidence:
            for i, evidence in enumerate(brief.evidence, 1):
                st.write(f"**Source [{i}]:** {evidence.source}")
                st.text(evidence.snippet)
                st.divider()
        else:
            st.info("No evidence found")

def main():
    """Main Streamlit app."""
    
    # Initialize database
    db = init_database()
    
    # Initialize session state
    if "current_meeting_id" not in st.session_state:
        st.session_state.current_meeting_id = None
    if "materials_added" not in st.session_state:
        st.session_state.materials_added = []
    if "generated_brief" not in st.session_state:
        st.session_state.generated_brief = None
    if "show_download_options" not in st.session_state:
        st.session_state.show_download_options = False
    if "qa_history" not in st.session_state:
        st.session_state.qa_history = []
    
    # Title
    st.title("🧠 Executive Intelligence Copilot")
    st.markdown("_Prepare for meetings in minutes, not hours._")
    
    # Sidebar
    with st.sidebar:
        st.header("Meeting Preparation")
        
        # Tab 1: Create/Select Meeting
        st.subheader("📅 Meeting Selection")
        meeting_action = st.radio(
            "What would you like to do?",
            ["Create New Meeting", "Select Existing Meeting"]
        )
        
        if meeting_action == "Create New Meeting":
            st.write("**Create a New Meeting**")
            meeting_title = st.text_input("Meeting Title", placeholder="e.g., AI Roadmap Sync")
            meeting_date = st.date_input("Meeting Date")
            attendees = st.text_input("Attendees (CSV)", placeholder="John, Jane, Bob")
            tags = st.text_input("Tags (CSV)", placeholder="strategy, planning")
            
            if st.button("✅ Create Meeting"):
                if meeting_title:
                    # Convert date to string
                    date_str = meeting_date.strftime("%Y-%m-%d") if meeting_date else None
                    
                    # Create meeting in database
                    meeting_id = db.create_meeting(
                        title=meeting_title,
                        date=date_str,
                        attendees=attendees if attendees else None,
                        tags=tags if tags else None
                    )
                    
                    # Store in session state
                    st.session_state.current_meeting_id = meeting_id
                    st.session_state.generated_brief = None
                    
                    st.success(f"✅ Meeting '{meeting_title}' created successfully!")
                    st.info(f"Meeting ID: {meeting_id}")
                    st.rerun()  # Refresh to show in dropdown
                else:
                    st.error("Please enter a meeting title")
        
        else:  # Select Existing
            st.write("**Select Existing Meeting**")
            
            # Fetch all meetings from database
            meetings = db.list_meetings()
            
            if meetings:
                # Create a list of meeting display names
                meeting_options = [f"{m['title']} ({m['date'] or 'No date'})" for m in meetings]
                meeting_ids = [m['id'] for m in meetings]
                
                selected_index = st.selectbox(
                    "Choose a meeting",
                    range(len(meeting_options)),
                    format_func=lambda x: meeting_options[x]
                )
                
                if selected_index is not None:
                    selected_meeting_id = meeting_ids[selected_index]
                    st.session_state.current_meeting_id = selected_meeting_id
                    st.session_state.generated_brief = None
                    
                    # Display meeting details
                    selected_meeting = meetings[selected_index]
                    st.info(f"""
                    **Selected:** {selected_meeting['title']}  
                    **Date:** {selected_meeting['date'] or 'Not set'}  
                    **Created:** {selected_meeting['created_at'][:10]}
                    """)
            else:
                st.info("No meetings found. Create a new meeting first!")
                st.session_state.current_meeting_id = None
        
        st.divider()
        
        # Tab 2: Upload/Paste Materials
        st.subheader("📎 Add Materials")
        
        # Check if a meeting is selected
        if st.session_state.current_meeting_id is None:
            st.warning("⚠️ Please create or select a meeting first!")
        else:
            material_source = st.radio(
                "How would you like to add materials?",
                ["Upload Files", "Paste Text"]
            )
            
            if material_source == "Upload Files":
                uploaded_files = st.file_uploader(
                    "Upload PDF, DOCX, PPTX, or TXT files",
                    type=["pdf", "docx", "pptx", "txt"],
                    accept_multiple_files=True
                )
                
                if uploaded_files and st.button("📤 Upload Files"):
                    meeting_id = st.session_state.current_meeting_id
                    success_count = 0
                    error_count = 0
                    
                    for uploaded_file in uploaded_files:
                        try:
                            # Read file content
                            file_bytes = uploaded_file.read()
                            
                            # Parse file
                            text, media_type = parse_file(file_bytes, uploaded_file.name)
                            
                            if text:
                                # Save to database
                                material_id = db.add_material(
                                    meeting_id=meeting_id,
                                    filename=uploaded_file.name,
                                    media_type=media_type,
                                    text=text
                                )
                                success_count += 1
                                st.success(f"✅ Uploaded: {uploaded_file.name} ({len(text)} chars)")
                            else:
                                error_count += 1
                                st.warning(f"⚠️ Could not parse: {uploaded_file.name}")
                        except Exception as e:
                            error_count += 1
                            st.error(f"❌ Error uploading {uploaded_file.name}: {str(e)}")
                    
                    if success_count > 0:
                        st.session_state.generated_brief = None
                        st.balloons()  # Celebrate!
                        st.rerun()  # Refresh materials table
            
            else:  # Paste Text
                pasted_text = st.text_area(
                    "Paste meeting notes, emails, or other text",
                    height=150,
                    placeholder="Paste your content here..."
                )
                
                if pasted_text and st.button("📝 Save Pasted Text"):
                    meeting_id = st.session_state.current_meeting_id
                    
                    # Parse pasted text
                    text, media_type = parse_pasted_text(pasted_text)
                    
                    if text:
                        # Save to database
                        material_id = db.add_material(
                            meeting_id=meeting_id,
                            filename="pasted_text.txt",
                            media_type=media_type,
                            text=text
                        )
                        st.success(f"✅ Saved pasted text ({len(text)} characters)")
                        st.session_state.generated_brief = None
                        st.balloons()
                        st.rerun()  # Refresh materials table
                    else:
                        st.warning("⚠️ No text to save")
        
        st.divider()
        
        # Tab 3: Actions
        st.subheader("⚡ Actions")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("🎯 Generate Brief", use_container_width=True):
                if not st.session_state.current_meeting_id:
                    st.warning("Please select a meeting first")
                else:
                    materials = db.get_materials(st.session_state.current_meeting_id)
                    if not materials:
                        st.warning("No materials found. Upload or paste materials first!")
                    else:
                        try:
                            with st.spinner("Generating brief..."):
                                orchestrator = init_orchestrator()
                                current_meeting = db.get_meeting(st.session_state.current_meeting_id)
                                
                                result = orchestrator.generate_brief(
                                    meeting_id=st.session_state.current_meeting_id,
                                    title=current_meeting['title'],
                                    date=current_meeting['date'] or "Today"
                                )
                                
                                if result.get("success"):
                                    st.session_state.generated_brief = result["brief"]
                                    provider = result.get("provider", "unknown")
                                    st.success("Brief generated successfully (provider: {})".format(provider))
                                    st.rerun()
                                else:
                                    st.error("Error: {}".format(result.get("error", "Unknown error")))
                        
                        except Exception as e:
                            st.error("Error generating brief: {}".format(str(e)))
        
        with col2:
            if st.button("🔍 What happened last time?", use_container_width=True):
                if st.session_state.current_meeting_id:
                    try:
                        orchestrator = init_orchestrator()
                        previous_brief = orchestrator.recall_previous_brief(
                            st.session_state.current_meeting_id
                        )
                        if previous_brief:
                            st.session_state.generated_brief = previous_brief
                            st.success("Previous brief retrieved successfully")
                            st.rerun()
                        else:
                            st.warning("No previous brief found for this meeting")
                    except Exception as e:
                        st.error("Error recalling previous brief: {}".format(str(e)))
                else:
                    st.warning("Please select a meeting first")
        
        with col3:
            if st.button("💾 Download Brief", use_container_width=True):
                if st.session_state.generated_brief:
                    st.session_state.show_download_options = True
                else:
                    st.warning("Generate a brief first")
        
        # Download options (shown when button clicked)
        if st.session_state.get("show_download_options", False) and st.session_state.generated_brief:
            st.divider()
            st.subheader("💾 Download Options")
            
            download_col1, download_col2, download_col3 = st.columns([1, 1, 2])
            
            with download_col1:
                brief_dict = st.session_state.generated_brief.model_dump()
                json_str = json.dumps(brief_dict, indent=2)
                st.download_button(
                    label="📄 Download JSON",
                    data=json_str,
                    file_name="meeting_brief_{}.json".format(
                        datetime.now().strftime("%Y%m%d_%H%M%S")
                    ),
                    mime="application/json",
                    use_container_width=True
                )
            
            with download_col2:
                markdown_content = convert_brief_to_markdown(st.session_state.generated_brief)
                st.download_button(
                    label="📝 Download Markdown",
                    data=markdown_content,
                    file_name="meeting_brief_{}.md".format(
                        datetime.now().strftime("%Y%m%d_%H%M%S")
                    ),
                    mime="text/markdown",
                    use_container_width=True
                )
            
            with download_col3:
                if st.button("❌ Close", use_container_width=True):
                    st.session_state.show_download_options = False
                    st.rerun()
        
        # Brief History Dropdown
        if st.session_state.current_meeting_id:
            st.divider()
            brief_history = db.get_brief_history(st.session_state.current_meeting_id)
            
            if brief_history and len(brief_history) > 1:
                st.subheader("📚 Brief History")
                
                history_options = [
                    "Generated on {} using {}".format(
                        b['created_at'][:19], 
                        b['model'].upper()
                    ) 
                    for b in brief_history
                ]
                
                selected_brief_idx = st.selectbox(
                    "View previous versions",
                    range(len(history_options)),
                    format_func=lambda x: history_options[x]
                )
                
                if st.button("📖 Load Selected Brief", use_container_width=True):
                    try:
                        selected_brief_id = brief_history[selected_brief_idx]['id']
                        brief_data = db.get_brief_by_id(selected_brief_id)
                        
                        if brief_data:
                            st.session_state.generated_brief = MeetingBrief(**brief_data["brief"])
                            st.success("Historical brief loaded")
                            st.rerun()
                    except Exception as e:
                        st.error("Error loading brief: {}".format(str(e)))
    
    # Main content area
    st.header("📊 Meeting Brief")
    
    # Q&A Section (render after actions)
    render_qa_section()
    
    # Show current meeting info
    if st.session_state.current_meeting_id:
        current_meeting = db.get_meeting(st.session_state.current_meeting_id)
        if current_meeting:
            st.info(f"**Current Meeting:** {current_meeting['title']} | **Date:** {current_meeting['date'] or 'Not set'}")
    else:
        st.info("👈 Please create or select a meeting in the sidebar to get started")
    
    # Display generated brief
    if st.session_state.generated_brief:
        st.success("✅ Brief generated! See details below:")
        render_brief(st.session_state.generated_brief)
    else:
        # Show placeholder tabs
        tab1, tab2, tab3, tab4 = st.tabs(["Recap", "Open Items", "Key Topics", "Agenda"])
        
        with tab1:
            st.subheader("Last Meeting Recap")
            st.info("*Click 'Generate Brief' to populate*")
        
        with tab2:
            st.subheader("Open Action Items")
            st.info("*Click 'Generate Brief' to populate*")
        
        with tab3:
            st.subheader("Key Topics Today")
            st.info("*Click 'Generate Brief' to populate*")
        
        with tab4:
            st.subheader("Proposed Agenda")
            st.info("*Click 'Generate Brief' to populate*")
    
    st.divider()
    
    # Materials table
    st.subheader("📁 Materials Added")
    
    if st.session_state.current_meeting_id:
        # Fetch materials from database
        materials = db.get_materials(st.session_state.current_meeting_id)
        
        if materials:
            # Create a DataFrame for better display
            import pandas as pd
            
            # Prepare data for display
            display_data = []
            for mat in materials:
                display_data.append({
                    "Filename": mat['filename'],
                    "Type": mat['media_type'].upper(),
                    "Characters": f"{mat['char_count']:,}",
                    "Added": mat['created_at'][:19]  # Show date and time
                })
            
            df = pd.DataFrame(display_data)
            st.dataframe(df, use_container_width=True, hide_index=True)
            
            # Summary
            total_chars = sum([m['char_count'] for m in materials])
            st.caption(f"📊 Total: {len(materials)} material(s) | {total_chars:,} total characters")
        else:
            st.info("No materials added yet. Upload files or paste text in the sidebar.")
    else:
        st.info("👈 Please create or select a meeting to see materials")


if __name__ == "__main__":
    main()
