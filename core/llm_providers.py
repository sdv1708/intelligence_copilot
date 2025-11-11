"""LLM Provider Factory using LangChain."""

from langchain_openai import ChatOpenAI
from langchain_anthropic  import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI
from core.utils import get_env, log_message


def get_llm_provider(provider_name: str = None):
    """
    Get LLM provider using LangChain.
    
    Args:
        provider_name: 'gemini', 'openai', or 'anthropic'
    
    Returns:
        LangChain LLM instance
    """
    provider_name = (provider_name or get_env("LLM_PROVIDER", "gemini")).lower()
    
    try:
        if provider_name == "gemini":
            log_message("INFO", "Initializing Google Gemini")
            api_key = get_env("GEMINI_API_KEY")
            return ChatGoogleGenerativeAI(
                model="gemini-2.5-flash",
                google_api_key=api_key,
                temperature=0.7,
                max_output_tokens=3000
            )
        
        elif provider_name == "openai":
            log_message("INFO", "Initializing OpenAI GPT-4")
            api_key = get_env("OPENAI_API_KEY")
            return ChatOpenAI(
                model="gpt-4",
                openai_api_key=api_key,
                temperature=0.7,
                max_tokens=3000
            )
        
        elif provider_name == "anthropic":
            log_message("INFO", "Initializing Anthropic Claude")
            api_key = get_env("ANTHROPIC_API_KEY")
            return ChatAnthropic(
                model="claude-3-5-sonnet-20241022",
                anthropic_api_key=api_key,
                temperature=0.7,
                max_tokens=3000
            )
        
        else:
            raise ValueError("Unknown provider: {}".format(provider_name))
    
    except Exception as e:
        log_message("ERROR", "Failed to initialize LLM: {}".format(str(e)))
        raise