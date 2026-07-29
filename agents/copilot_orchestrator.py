"""Multi-agent orchestrator using LangChain."""
from core.db import Database
from core.parsing import parse_file
from core.indexing import index_material
from core.recall import Retriever
from core.schema import MeetingBrief
from core.llm_providers import get_llm_provider
from core.synthesis import Synthesizer
from core.utils import log_message
import json


class CopilotOrchestrator:
    """Multi-agent system using LangChain."""

    def __init__(self, provider: str = "gemini"):
        self.db = Database()
        self.llm = get_llm_provider(provider)
        self.provider_name = provider
        self.retriever = Retriever(self.db)
        self.synthesizer = Synthesizer(self.llm, provider=provider)

        log_message("INFO", "Orchestrator initialized with {} ({})".format(
            provider, self.synthesizer.model_name
        ))
    
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
            
            # Check if material already exists in DB (to avoid duplicates)
            # If it exists, get the material_id, otherwise create new
            materials = self.db.get_materials(meeting_id)
            material_id = None
            for mat in materials:
                if mat['filename'] == filename:
                    material_id = mat['id']
                    log_message("INFO", "[IngestionTool] Material already exists: {}".format(material_id))
                    break
            
            # Save to DB only if it doesn't exist
            if not material_id:
                material_id = self.db.add_material(
                    meeting_id=meeting_id,
                    filename=filename,
                    media_type=media_type,
                    text=text
                )
            
            # Chunk, embed and index in one step. `index_material` stores the
            # chunks as rows and indexes their primary keys, so a re-upload
            # replaces the previous chunks and their vectors instead of
            # appending a duplicate copy of the document to the index.
            chunk_ids = index_material(self.db, material_id)
            if not chunk_ids:
                log_message("WARNING", "[IngestionTool] No chunks created")
                return json.dumps({"success": False, "error": "No chunks created"})

            log_message("OK", "[IngestionTool] Ingested: {} ({} chunks)".format(
                filename, len(chunk_ids)
            ))

            return json.dumps({
                "success": True,
                "material_id": material_id,
                "chunks": len(chunk_ids)
            })
        
        except Exception as e:
            log_message("ERROR", "[IngestionTool] Error: {}".format(str(e)))
            return json.dumps({"success": False, "error": str(e)})
    
    def _recall(self, meeting_id: str, query: str = "", k: int = 8):
        """Retrieve context, returning the scored chunks and their rendered form.

        Both are needed downstream: the text goes into the prompt, and the
        objects carry the chunk ids that turn a citation into something
        checkable rather than something trusted.
        """
        results = self.retriever.recall(meeting_id, query=query, k=k)
        if not results:
            return [], ""
        return results, self.retriever.format_context(results, meeting_id)

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

            results, context_blocks = self._recall(meeting_id, k=k)

            if not results:
                log_message("WARNING", "[RecallTool] No context found")
                return json.dumps({"success": False})

            log_message("OK", "[RecallTool] Retrieved {} chunks".format(len(results)))

            return json.dumps({
                "success": True,
                "chunks": len(results),
                "context_blocks": context_blocks
            })

        except Exception as e:
            log_message("ERROR", "[RecallTool] Error: {}".format(str(e)))
            return json.dumps({"success": False, "error": str(e)})
    
    def _get_previous_meeting_brief(self, current_meeting_id: str, title: str):
        """
        Get the stored brief from the most recent meeting with the same title.
        Enables cross-meeting memory for recurring meetings.

        Args:
            current_meeting_id: Current meeting ID (to exclude)
            title: Meeting title to match

        Returns:
            The previous brief as a raw dict, or None. Rendering it for the
            prompt is `core.synthesis.format_previous_brief`'s job -- keeping
            the two apart means the same memory can be handed to a LangGraph
            node in Chunk 5 without dragging a prompt fragment along with it.
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
                return None

            # Get most recent meeting (by created_at)
            most_recent = max(same_title_meetings, key=lambda x: x['created_at'])
            log_message("INFO", "[Step 0] Found previous meeting: {} from {}".format(
                most_recent['title'], most_recent['date'] or most_recent['created_at'][:10]
            ))
            
            # Get brief from that meeting
            prev_brief = self.db.get_latest_brief(most_recent['id'])
            
            if not prev_brief:
                log_message("INFO", "[Step 0] Previous meeting has no brief yet")
                return None

            log_message("OK", "[Step 0] Carrying context from previous meeting")
            return prev_brief['brief']

        except Exception as e:
            log_message("ERROR", "[Step 0] Error getting previous meeting context: {}".format(str(e)))
            return None
    
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
            previous_brief = self._get_previous_meeting_brief(meeting_id, title)

            # Step 1: Recall
            log_message("INFO", "[Step 1] Recalling context")
            results, context_blocks = self._recall(meeting_id)

            if not results:
                return {"success": False, "error": "Recall failed"}

            # Step 2: Synthesis
            #
            # The model is asked for a MeetingBrief through the provider's own
            # structured-output channel, so there is no markdown fence to strip,
            # no trailing comma to regex away, and no truncated object to repair
            # by counting braces. What comes back either validates or raises.
            log_message("INFO", "[Step 2] Synthesizing brief")

            synthesis = self.synthesizer.brief(
                title=title,
                date=date,
                results=results,
                context=context_blocks,
                previous_brief=previous_brief,
            )
            brief = synthesis.brief

            if synthesis.dropped_sources:
                log_message("WARNING", "[Step 2] Discarded {} unmatched citation(s)".format(
                    len(synthesis.dropped_sources)
                ))

            log_message("OK", "[Step 2] Brief synthesized ({} citations resolved)".format(
                len(synthesis.cited_chunk_ids)
            ))
            
            # Step 3: Memory (Store)
            log_message("INFO", "[Step 3] Storing brief")
            
            brief_id = self.db.save_brief(
                meeting_id=meeting_id,
                model=synthesis.model,
                brief_dict=brief.model_dump()
            )

            log_message("OK", "[Step 3] Brief stored: {}".format(brief_id))

            log_message("INFO", "=== Brief Generation Complete ===")

            return {
                "success": True,
                "brief": brief,
                "brief_id": brief_id,
                "provider": self.provider_name,
                "model": synthesis.model
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

            results, context_blocks = self._recall(
                meeting_id,
                query=question,
                k=self.retriever.settings.qa_retrieval_k,
            )

            if not results:
                log_message("WARNING", "[QA] No relevant context found")
                return {
                    "success": True,
                    "answer": "I could not find relevant information in the documents to answer this question.",
                    "sources": [],
                    "provider": self.provider_name
                }

            # Step 2: Answer against that context
            #
            # Sources come from the chunks that were actually retrieved, not
            # from a regex over the rendered prompt. The old regex looked for
            # "Source: " in text that never contained it, so every answer was
            # returned with an empty source list.
            log_message("INFO", "[QA-Step 2] Calling LLM for answer")

            answer = self.synthesizer.answer(
                question=question,
                results=results,
                context=context_blocks,
            )

            log_message("OK", "[QA] Question answered ({} sources)".format(
                len(answer.sources)
            ))

            return {
                "success": True,
                "answer": answer.text,
                "sources": list(answer.sources),
                "provider": self.provider_name,
                "model": answer.model
            }
        
        except Exception as e:
            log_message("ERROR", "[QA] Error answering question: {}".format(str(e)))
            return {"success": False, "error": str(e)}
