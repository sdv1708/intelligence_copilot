"""LLM synthesis using Gemini 1.5 Flash."""

from typing import Dict, Any, Optional
import json
from core.utils import get_env, log_message
from core.schema import MeetingBrief


def load_prompt_template(prompt_file: str) -> str:
    """Load a prompt template from file."""
    try:
        with open(prompt_file, "r") as f:
            return f.read()
    except Exception as e:
        log_message("ERROR", f"Failed to load prompt {prompt_file}: {str(e)}")
        return ""


def build_user_prompt(title: str, date: str, context_blocks: str) -> str:
    """
    Build the user prompt with meeting details and context.
    
    Args:
        title: Meeting title
        date: Meeting date
        context_blocks: Formatted context from recall
    
    Returns:
        Formatted user prompt
    """
    template = load_prompt_template("prompts/user_prompt.txt")
    
    user_prompt = template.replace("{{title}}", title)
    user_prompt = user_prompt.replace("{{date}}", date)
    user_prompt = user_prompt.replace("{{context_blocks}}", context_blocks)
    
    return user_prompt


def call_gemini(system_prompt: str, user_prompt: str) -> Dict[str, Any]:
    """
    Call Google Gemini 1.5 Flash API and return JSON.
    
    Args:
        system_prompt: System instructions
        user_prompt: User query with context
    
    Returns:
        Parsed JSON response
    """
    try:
        import google.generativeai as genai
    except ImportError:
        log_message("ERROR", "google-generativeai not installed")
        return {}
    
    api_key = get_env("GEMINI_API_KEY")
    if not api_key:
        log_message("ERROR", "GEMINI_API_KEY not set")
        return {}
    
    genai.configure(api_key=api_key)
    
    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content(
            [system_prompt, user_prompt],
            generation_config=genai.types.GenerationConfig(
                temperature=0.3,
                max_output_tokens=2000
            )
        )
        
        text = response.text.strip()
        log_message("INFO", f"Gemini response received ({len(text)} chars)")
        
        # Attempt to extract JSON from response
        # Look for JSON block if wrapped in markdown
        if "```json" in text:
            start = text.find("```json") + 7
            end = text.find("```", start)
            text = text[start:end].strip()
        elif text.startswith("```"):
            start = text.find("\n") + 1
            end = text.rfind("```")
            text = text[start:end].strip()
        
        result = json.loads(text)
        return result
    
    except json.JSONDecodeError as e:
        log_message("ERROR", f"Failed to parse Gemini JSON response: {str(e)}")
        return {}
    except Exception as e:
        log_message("ERROR", f"Gemini API error: {str(e)}")
        return {}


def generate_brief(title: str, date: str, context_blocks: str) -> Optional[MeetingBrief]:
    """
    Generate a meeting brief using LLM.
    
    Args:
        title: Meeting title
        date: Meeting date
        context_blocks: Formatted context from retrieval
    
    Returns:
        MeetingBrief object or None on failure
    """
    log_message("INFO", f"Generating brief for '{title}' on {date}")
    
    # Load prompts
    system_prompt = load_prompt_template("prompts/system_prompt.txt")
    user_prompt = build_user_prompt(title, date, context_blocks)
    
    # Call LLM
    response_dict = call_gemini(system_prompt, user_prompt)
    
    if not response_dict:
        log_message("ERROR", "No valid response from Gemini")
        return None
    
    # Validate with Pydantic
    try:
        brief = MeetingBrief(**response_dict)
        log_message("INFO", "Brief successfully validated")
        return brief
    except Exception as e:
        log_message("ERROR", f"Brief validation failed: {str(e)}")
        return None

