"""Multi-agent orchestrator using LangChain."""
# from langchain.prompts import PromptTemplate
from core.db import Database
from core.parsing import parse_file
from core.chunk import chunk_text
from core.embed import encode, build_or_load_index, add_to_index
from core.recall import recall_context, format_context_blocks
from core.synth import load_prompt_template
from core.schema import MeetingBrief
from core.llm_providers import get_llm_provider
from core.utils import log_message, generate_id
import json
import os
import re
import time


class CopilotOrchestrator:
    """Multi-agent system using LangChain."""
    
    def __init__(self, provider: str = "gemini"):
        self.db = Database()
        self.llm = get_llm_provider(provider)
        self.provider_name = provider
        
        log_message("INFO", "Orchestrator initialized with {}".format(provider))
    
    def ingest_material(self, file_bytes: bytes, filename: str, meeting_id: str) -> dict:
        """
        Ingest material (Tool for LangChain).
        
        Args:
            file_bytes: File content
            filename: Original filename
            meeting_id: Meeting ID
        
        Returns:
            Result dictionary
        """
        try:
            log_message("INFO", "[IngestionTool] Processing: {}".format(filename))
            
            # Parse
            text, media_type = parse_file(file_bytes, filename)
            if not text:
                log_message("WARNING", "[IngestionTool] Failed to parse")
                return json.dumps({"success": False})
            
            # Save to DB
            material_id = self.db.add_material(
                meeting_id=meeting_id,
                filename=filename,
                media_type=media_type,
                text=text
            )
            
            # Chunk and embed
            chunks = chunk_text(text)
            embeddings = encode(chunks)
            
            # Index in FAISS
            from core.utils import get_storage_path
            faiss_path = "{}/{}.index".format(
                os.getenv("FAISS_PATH", get_storage_path("faiss")),
                meeting_id
            )
            index = build_or_load_index(faiss_path)
            add_to_index(index, embeddings)
            
            log_message("OK", "[IngestionTool] Ingested: {}".format(filename))
            
            return json.dumps({
                "success": True,
                "material_id": material_id,
                "chunks": len(chunks)
            })
        
        except Exception as e:
            log_message("ERROR", "[IngestionTool] Error: {}".format(str(e)))
            return json.dumps({"success": False, "error": str(e)})
    
    def recall_context_tool(self, meeting_id: str, k: int = 8) -> str:
        """
        Recall context (Tool for LangChain).
        
        Args:
            meeting_id: Meeting ID
            k: Number of results
        
        Returns:
            Context blocks as JSON string
        """
        try:
            log_message("INFO", "[RecallTool] Retrieving context for: {}".format(meeting_id))
            
            db_conn = self.db.get_connection()
            context = recall_context(db_conn, meeting_id, query="", k=k)
            db_conn.close()
            
            if not context:
                log_message("WARNING", "[RecallTool] No context found")
                return json.dumps({"success": False})
            
            context_blocks = format_context_blocks(context)
            log_message("OK", "[RecallTool] Retrieved {} chunks".format(len(context)))
            
            return json.dumps({
                "success": True,
                "chunks": len(context),
                "context_blocks": context_blocks
            })
        
        except Exception as e:
            log_message("ERROR", "[RecallTool] Error: {}".format(str(e)))
            return json.dumps({"success": False, "error": str(e)})
    
    def _get_previous_meeting_context(self, current_meeting_id: str, title: str) -> str:
        """
        Get context from previous meetings with the same title.
        Enables cross-meeting memory for recurring meetings.
        
        Args:
            current_meeting_id: Current meeting ID (to exclude)
            title: Meeting title to match
        
        Returns:
            Formatted context string from previous meeting, or empty string
        """
        try:
            # Get all meetings with same title
            all_meetings = self.db.list_meetings()
            same_title_meetings = [
                m for m in all_meetings 
                if m['title'].lower().strip() == title.lower().strip() 
                and m['id'] != current_meeting_id
            ]
            
            if not same_title_meetings:
                log_message("INFO", "[Step 0] No previous meetings found with title: {}".format(title))
                return ""
            
            # Get most recent meeting (by created_at)
            most_recent = max(same_title_meetings, key=lambda x: x['created_at'])
            log_message("INFO", "[Step 0] Found previous meeting: {} from {}".format(
                most_recent['title'], most_recent['date'] or most_recent['created_at'][:10]
            ))
            
            # Get brief from that meeting
            prev_brief = self.db.get_latest_brief(most_recent['id'])
            
            if not prev_brief:
                log_message("INFO", "[Step 0] Previous meeting has no brief yet")
                return ""
            
            # Format previous meeting context
            brief_data = prev_brief['brief']
            context = "=" * 60 + "\n"
            context += "PREVIOUS MEETING CONTEXT\n"
            context += "=" * 60 + "\n\n"
            context += "Previous Meeting: {}\n".format(most_recent['title'])
            context += "Date: {}\n\n".format(most_recent['date'] or 'Not specified')
            
            context += "LAST MEETING SUMMARY:\n"
            context += "{}\n\n".format(brief_data.get('last_meeting_recap', 'No recap available'))
            
            # Add action items if present
            action_items = brief_data.get('open_action_items', [])
            if action_items:
                context += "ACTION ITEMS FROM LAST TIME:\n"
                for item in action_items[:5]:  # Top 5 items
                    context += "- {}: {} (Status: {})\n".format(
                        item.get('owner', 'TBD'),
                        item.get('item', ''),
                        item.get('status', 'open')
                    )
                context += "\n"
            
            # Add key topics if present
            key_topics = brief_data.get('key_topics_today', [])
            if key_topics:
                context += "KEY TOPICS DISCUSSED:\n"
                for topic in key_topics[:3]:  # Top 3 topics
                    context += "- {}\n".format(topic)
                context += "\n"
            
            context += "=" * 60 + "\n\n"
            
            log_message("OK", "[Step 0] Added context from previous meeting")
            return context
            
        except Exception as e:
            log_message("ERROR", "[Step 0] Error getting previous meeting context: {}".format(str(e)))
            return ""
    
    def generate_brief(self, meeting_id: str, title: str, date: str) -> dict:
        """
        Main workflow: Generate brief using LangChain agents.
        
        Args:
            meeting_id: Meeting ID
            title: Meeting title
            date: Meeting date
        
        Returns:
            Generated brief
        """
        log_message("INFO", "=== Starting Brief Generation ===")
        
        try:
            # Step 0: Check for previous meetings with same title (cross-meeting memory)
            log_message("INFO", "[Step 0] Checking for previous meetings")
            previous_meeting_context = self._get_previous_meeting_context(meeting_id, title)
            
            # Step 1: Recall
            log_message("INFO", "[Step 1] Recalling context")
            recall_result = json.loads(self.recall_context_tool(meeting_id))
            
            if not recall_result.get("success"):
                return {"success": False, "error": "Recall failed"}
            
            context_blocks = recall_result["context_blocks"]
            
            # Step 2: Synthesis (using LLMChain)
            log_message("INFO", "[Step 2] Synthesizing brief")
            
            system_prompt = load_prompt_template("prompts/system_prompt.txt")
            user_template = load_prompt_template("prompts/user_prompt.txt")
            
            # Build final prompt
            user_prompt = user_template.replace("{{title}}", title)
            user_prompt = user_prompt.replace("{{date}}", date)
            user_prompt = user_prompt.replace("{{context_blocks}}", context_blocks)
            
            # Add previous meeting context if available
            if previous_meeting_context:
                user_prompt = previous_meeting_context + "\n\n" + user_prompt
            
            # Call LLM
            from langchain_core.messages import HumanMessage, SystemMessage
            
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ]
            
            # Try up to 2 times to get valid JSON
            max_retries = 2
            brief_dict = None
            
            for attempt in range(max_retries):
                try:
                    response = self.llm.invoke(messages)
                    response_text = response.content if hasattr(response, 'content') else str(response)
                    
                    # Check if response is empty
                    if not response_text or not response_text.strip():
                        log_message("WARNING", "[Step 2] Empty response from LLM (attempt {})".format(attempt + 1))
                        if attempt < max_retries - 1:
                            log_message("INFO", "[Step 2] Retrying...")
                            time.sleep(2)
                            continue
                        else:
                            return {"success": False, "error": "LLM returned empty response. Please try again."}
                    
                    # Parse JSON - handle markdown code fences robustly
                    response_text = response_text.strip()
                    
                    # Extract JSON from markdown code blocks
                    if "```json" in response_text:
                        start = response_text.find("```json") + 7
                        end = response_text.find("```", start)
                        if end != -1:
                            response_text = response_text[start:end].strip()
                    elif "```" in response_text:
                        start = response_text.find("```") + 3
                        newline_pos = response_text.find("\n", start)
                        if newline_pos != -1:
                            start = newline_pos + 1
                        end = response_text.find("```", start)
                        if end != -1:
                            response_text = response_text[start:end].strip()
                    
                    # If still no JSON object, try to extract it
                    if not response_text.startswith("{"):
                        start = response_text.find("{")
                        end = response_text.rfind("}") + 1
                        if start != -1 and end > start:
                            response_text = response_text[start:end]
                        else:
                            # No JSON found in response
                            log_message("WARNING", "[Step 2] No JSON found in response (attempt {})".format(attempt + 1))
                            log_message("WARNING", "[Step 2] Response preview: {}".format(response_text[:200]))
                            if attempt < max_retries - 1:
                                log_message("INFO", "[Step 2] Retrying with clearer prompt...")
                                # Add more explicit instruction
                                messages[-1].content = user_prompt + "\n\nIMPORTANT: You must return ONLY valid JSON. No explanations, no markdown, just the JSON object."
                                time.sleep(2)
                                continue
                            else:
                                # Save full response for debugging
                                try:
                                    debug_file = "debug_json_error_{}.txt".format(generate_id())
                                    with open(debug_file, 'w', encoding='utf-8') as f:
                                        f.write("Original response:\n" + str(response.content) + "\n\nExtracted text:\n" + response_text)
                                    log_message("ERROR", "[Step 2] Full response saved to: {}".format(debug_file))
                                except Exception as save_error:
                                    log_message("ERROR", "[Step 2] Could not save debug file: {}".format(str(save_error)))
                                
                                return {"success": False, "error": "LLM did not return valid JSON. Response may be empty or malformed. Please try again."}
                    
                    # Clean common JSON syntax errors
                    # Remove trailing commas before closing brackets/braces
                    response_text = re.sub(r',(\s*[}\]])', r'\1', response_text)
                    # Remove any comments (// style)
                    response_text = re.sub(r'//[^\n]*', '', response_text)
                    # Remove any comments (/* */ style)
                    response_text = re.sub(r'/\*.*?\*/', '', response_text, flags=re.DOTALL)
                    
                    # Parse JSON
                    brief_dict = json.loads(response_text)
                    log_message("OK", "[Step 2] Successfully parsed JSON (attempt {})".format(attempt + 1))
                    break  # Success, exit retry loop
                    
                except json.JSONDecodeError as e:
                    log_message("WARNING", "[Step 2] JSON parse error (attempt {}): {}".format(attempt + 1, str(e)))
                    log_message("WARNING", "[Step 2] Problematic JSON (first 500 chars): {}".format(response_text[:500] if response_text else "EMPTY"))
                    
                    if attempt < max_retries - 1:
                        log_message("INFO", "[Step 2] Retrying...")
                        # Add more explicit instruction
                        messages[-1].content = user_prompt + "\n\nCRITICAL: Return ONLY valid JSON matching the schema. No markdown, no explanations, no extra text. Just the JSON object."
                        time.sleep(2)
                        continue
                    else:
                        # Save full response for debugging
                        try:
                            debug_file = "debug_json_error_{}.txt".format(generate_id())
                            with open(debug_file, 'w', encoding='utf-8') as f:
                                f.write("Original response:\n" + str(response.content if hasattr(response, 'content') else response) + "\n\nExtracted text:\n" + (response_text if response_text else "EMPTY"))
                            log_message("ERROR", "[Step 2] Full response saved to: {}".format(debug_file))
                        except Exception as save_error:
                            log_message("ERROR", "[Step 2] Could not save debug file: {}".format(str(save_error)))
                        
                        return {"success": False, "error": "Failed to parse LLM response after {} attempts: {}. Please try again or check your API key.".format(max_retries, str(e))}
                
                except Exception as e:
                    log_message("ERROR", "[Step 2] Unexpected error (attempt {}): {}".format(attempt + 1, str(e)))
                    if attempt < max_retries - 1:
                        time.sleep(2)
                        continue
                    else:
                        return {"success": False, "error": "Unexpected error during synthesis: {}. Please try again.".format(str(e))}
            
            if brief_dict is None:
                return {"success": False, "error": "Failed to generate valid JSON after {} attempts. Please try again.".format(max_retries)}
            
            brief = MeetingBrief(**brief_dict)
            
            log_message("OK", "[Step 2] Brief synthesized")
            
            # Step 3: Memory (Store)
            log_message("INFO", "[Step 3] Storing brief")
            
            brief_id = self.db.save_brief(
                meeting_id=meeting_id,
                model=self.provider_name,
                brief_dict=brief.model_dump()
            )
            
            log_message("OK", "[Step 3] Brief stored: {}".format(brief_id))
            
            log_message("INFO", "=== Brief Generation Complete ===")
            
            return {
                "success": True,
                "brief": brief,
                "brief_id": brief_id,
                "provider": self.provider_name
            }
        
        except Exception as e:
            log_message("ERROR", "Workflow failed: {}".format(str(e)))
            return {"success": False, "error": str(e)}
    
    def recall_previous_brief(self, meeting_id: str):
        """Recall previous brief."""
        log_message("INFO", "[MemoryTool] Recalling previous brief")
        result = self.db.get_latest_brief(meeting_id)
        if result:
            return MeetingBrief(**result["brief"])
        return None
    
    def answer_question(self, meeting_id: str, question: str) -> dict:
        """
        Answer a user question based on meeting materials.
        
        Args:
            meeting_id: Meeting ID
            question: User's question
        
        Returns:
            Dict with answer, sources, and metadata
        """
        log_message("INFO", "[QA] Answering question: {}".format(question[:50]))
        
        try:
            # Step 1: Recall context for the question
            log_message("INFO", "[QA-Step 1] Recalling relevant context")
            
            db_conn = self.db.get_connection()
            from core.recall import recall_context, format_context_blocks
            context = recall_context(db_conn, meeting_id, query=question, k=5)
            db_conn.close()
            
            if not context:
                log_message("WARNING", "[QA] No relevant context found")
                return {
                    "success": True,
                    "answer": "I could not find relevant information in the documents to answer this question.",
                    "sources": [],
                    "provider": self.provider_name
                }
            
            context_blocks = format_context_blocks(context)
            
            # Step 2: Load QA prompts
            log_message("INFO", "[QA-Step 2] Loading QA prompts")
            qa_system_prompt = load_prompt_template("prompts/qa_system_prompt.txt")
            qa_user_template = load_prompt_template("prompts/qa_user_prompt.txt")
            
            # Step 3: Build final prompt
            log_message("INFO", "[QA-Step 3] Building prompt with question")
            qa_user_prompt = qa_user_template.replace("{{question}}", question)
            qa_user_prompt = qa_user_prompt.replace("{{context_blocks}}", context_blocks)
            
            # Step 4: Call LLM
            log_message("INFO", "[QA-Step 4] Calling LLM for answer")
            from langchain_core.messages import HumanMessage, SystemMessage
            
            messages = [
                SystemMessage(content=qa_system_prompt),
                HumanMessage(content=qa_user_prompt)
            ]
            
            response = self.llm.invoke(messages)
            answer = response.content
            
            # Step 5: Extract sources from context
            log_message("INFO", "[QA-Step 5] Extracting sources")
            sources = self._extract_sources_from_context(context_blocks)
            
            log_message("OK", "[QA] Question answered successfully")
            
            return {
                "success": True,
                "answer": answer,
                "sources": sources,
                "provider": self.provider_name
            }
        
        except Exception as e:
            log_message("ERROR", "[QA] Error answering question: {}".format(str(e)))
            return {"success": False, "error": str(e)}
    
    def _extract_sources_from_context(self, context_blocks: str) -> list:
        """
        Extract source citations from context blocks.
        
        Args:
            context_blocks: Formatted context string
        
        Returns:
            List of unique sources
        """
        import re
        sources = []
        
        # Extract source references like "Source: mat_xxxxx#c5"
        pattern = r"Source: ([^\n]+)"
        matches = re.findall(pattern, context_blocks)
        
        # Get unique sources
        for match in matches:
            if match not in sources:
                sources.append(match)
        
        return sources[:5]  # Return top 5 sources
