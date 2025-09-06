from .llm_handler import LLMHandler, LLMResponse
from .validation import ParameterValidator, ValidationResult  
from .orchestrator import BackendOrchestrator, ProcessingResult, ProcessingStatus

__all__ = [
    # Core orchestrator
    "BackendOrchestrator",
    "ProcessingResult", 
    "ProcessingStatus",
    
    # LLM components
    "LLMHandler",
    "LLMResponse",
    
    # Validation components
    "ParameterValidator",
    "ValidationResult",
]

def create_backend(openai_api_key: str, **kwargs) -> BackendOrchestrator:
    """
    Convenience function to create a configured backend orchestrator.
    
    Args:
        openai_api_key: OpenAI API key
        **kwargs: Additional configuration options
        
    Returns:
        Configured BackendOrchestrator instance
    """
    config = {
        'openai_api_key': openai_api_key,
        **kwargs
    }
    return BackendOrchestrator(config)