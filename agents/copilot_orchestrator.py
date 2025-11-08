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
from core.utils import log_message
import json
import os


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
            faiss_path = "{}/{}.index".format(
                os.getenv("FAISS_PATH", "./data/faiss"),
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
            
            # Call LLM
            from langchain_core.messages import HumanMessage, SystemMessage
            
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ]
            
            response = self.llm.invoke(messages)
            response_text = response.content
            
            # Parse JSON
            if "" in response_text:
                start = response_text.find("") + 7
                end = response_text.find("```", start)
                response_text = response_text[start:end].strip()
            
            brief_dict = json.loads(response_text)
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
        return result["brief"] if result else None
