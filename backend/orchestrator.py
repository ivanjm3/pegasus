from typing import Dict, Any, Optional, Union, List, Tuple
from dataclasses import dataclass, asdict
from functools import lru_cache
import logging
from enum import Enum
from .llm_handler import LLMHandler, LLMResponse
from .validation import ParameterValidator, ValidationResult

logger = logging.getLogger(__name__)

class ProcessingStatus(Enum):
    """Status codes for processing results"""
    SUCCESS = "success"
    VALIDATION_ERROR = "validation_error"
    PARAMETER_NOT_FOUND = "parameter_not_found"
    LLM_ERROR = "llm_error"
    UNKNOWN_INTENT = "unknown_intent"
    SYSTEM_ERROR = "system_error"

@dataclass(frozen=True)
class ProcessingResult:
    """Immutable result structure for better type safety"""
    success: bool
    response: str
    intent: str
    status: ProcessingStatus
    parameter_name: Optional[str] = None
    parameter_value: Optional[Union[int, float, bool, str]] = None
    parameter_info: Optional[Dict[str, Any]] = None
    requires_confirmation: bool = False
    confidence: float = 0.0
    suggestions: Optional[List[str]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, excluding None values"""
        result = asdict(self)
        result['status'] = self.status.value
        return {k: v for k, v in result.items() if v is not None}

class BackendOrchestrator:
    __slots__ = ['_llm_handler', '_validator', '_config']
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize with dependency validation"""
        self._validate_config(config)
        self._config = config
        
        # Initialize components with error handling
        try:
            self._llm_handler = LLMHandler(
                api_key=config['openai_api_key'],
                model=config.get('llm_model', 'gpt-4'),
                px4_params_path=config.get('px4_params_path', 'data/px4_params.json')
            )
            self._validator = ParameterValidator(
                px4_params_path=config.get('px4_params_path', 'data/px4_params.json')
            )
            logger.info("Backend orchestrator initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize backend components: {e}")
            raise
    
    @staticmethod
    def _validate_config(config: Dict[str, Any]) -> None:
        """Validate configuration parameters"""
        required_keys = ['openai_api_key']
        missing_keys = [key for key in required_keys if not config.get(key)]
        
        if missing_keys:
            raise ValueError(f"Missing required config keys: {missing_keys}")
        
        # Validate API key format (basic check)
        api_key = config['openai_api_key']
        if not isinstance(api_key, str) or len(api_key) < 20:
            raise ValueError("Invalid OpenAI API key format")
    
    def _convert_conversation_history_to_hashable(self, conversation_history: Optional[List[Dict]]) -> Tuple:
        """Convert conversation history to a hashable format for caching"""
        if not conversation_history:
            return ()
        
        # Convert each message to a tuple for hashability
        return tuple(
            (msg.get('role', ''), msg.get('content', ''))
            for msg in conversation_history
        )
    
    @lru_cache(maxsize=128)  # Cache recent queries
    def _process_user_message_cached(self, user_message: str, conversation_history_tuple: Tuple) -> Dict[str, Any]:
        """Cached version that uses hashable conversation history"""
        # Convert tuple back to list of dicts
        conversation_history = [
            {'role': role, 'content': content}
            for role, content in conversation_history_tuple
        ] if conversation_history_tuple else None
        
        return self._process_user_message_impl(user_message, conversation_history)
    
    def _process_user_message_impl(self, user_message: str, conversation_history: Optional[List[Dict]]) -> Dict[str, Any]:
        """Actual implementation without caching"""
        if not user_message or not user_message.strip():
            return ProcessingResult(
                success=False,
                response="Please provide a message to process.",
                intent="error",
                status=ProcessingStatus.VALIDATION_ERROR
            ).to_dict()
        
        user_message = user_message.strip()
        
        try:
            # Process through LLM directly (no pre-classification needed)
            llm_response = self._llm_handler.process_query(user_message, conversation_history)
            
            # Handle LLM errors
            if llm_response.intent == 'error':
                return ProcessingResult(
                    success=False,
                    response=llm_response.explanation or "AI processing failed",
                    intent='error',
                    status=ProcessingStatus.LLM_ERROR
                ).to_dict()
            
            # Route to appropriate handler based on LLM's intent classification
            if llm_response.intent == 'explain':
                return self._handle_explanation(llm_response).to_dict()
            elif llm_response.intent == 'change':
                return self._handle_parameter_change(llm_response).to_dict()
            else:
                return self._handle_unknown_intent(llm_response).to_dict()
                
        except Exception as e:
            logger.error(f"Error processing message '{user_message[:50]}...': {e}", exc_info=True)
            return ProcessingResult(
                success=False,
                response="An unexpected error occurred while processing your request. Please try again.",
                intent='error',
                status=ProcessingStatus.SYSTEM_ERROR
            ).to_dict()
    
    def process_user_message(self, user_message: str, conversation_history: Optional[List[Dict]] = None) -> Dict[str, Any]:
        """Main method to process user messages with comprehensive error handling"""
        # Convert conversation history to hashable format for caching
        conversation_history_tuple = self._convert_conversation_history_to_hashable(conversation_history)
        return self._process_user_message_cached(user_message, conversation_history_tuple)
    
    def _handle_explanation(self, llm_response: LLMResponse) -> ProcessingResult:
        """Handle parameter explanation requests with enhanced information"""
        if not llm_response.parameter_name:
            return ProcessingResult(
                success=False,
                response="I couldn't identify which parameter you want explained. Please be more specific.",
                intent='explain',
                status=ProcessingStatus.PARAMETER_NOT_FOUND,
                suggestions=llm_response.suggestions or []
            )
        
        param_info = self._validator.get_parameter_info(llm_response.parameter_name)
        
        if not param_info:
            # Check if LLM provided suggestions, otherwise generate them
            suggestions = llm_response.suggestions or self._validator.get_similar_parameters(llm_response.parameter_name)
            error_msg = f"Parameter '{llm_response.parameter_name}' not found."
            if suggestions:
                error_msg += f" Did you mean: {', '.join(suggestions[:3])}?"
            
            return ProcessingResult(
                success=False,
                response=error_msg,
                intent='explain',
                status=ProcessingStatus.PARAMETER_NOT_FOUND,
                parameter_name=llm_response.parameter_name,
                suggestions=suggestions
            )
        
        # Use the validator's parameter summary for consistent formatting
        parameter_summary = self._validator.get_parameter_summary(llm_response.parameter_name)
        
        # Combine LLM explanation with technical details
        enhanced_explanation = self._build_explanation_response(
            llm_response.explanation, 
            parameter_summary, 
            param_info
        )
        
        return ProcessingResult(
            success=True,
            response=enhanced_explanation,
            intent='explain',
            status=ProcessingStatus.SUCCESS,
            parameter_name=llm_response.parameter_name,
            parameter_info=param_info,
            confidence=llm_response.confidence
        )
    
    def _build_explanation_response(self, llm_explanation: str, parameter_summary: str, param_info: Dict[str, Any]) -> str:
        """Build comprehensive explanation response"""
        response_parts = []
        
        # Add LLM explanation if available
        if llm_explanation and llm_explanation.strip():
            response_parts.append(llm_explanation.strip())
        
        # Add technical details
        if parameter_summary:
            response_parts.append(f"\nTechnical Details:\n{parameter_summary}")
        
        # Add usage hints for certain parameter types
        if param_info.get('enum_values'):
            response_parts.append(f"\nAllowed values: {', '.join(map(str, param_info['enum_values']))}")
        
        if param_info.get('unit'):
            response_parts.append(f"Unit: {param_info['unit']}")
        
        return "\n\n".join(response_parts)
    
    def _handle_parameter_change(self, llm_response: LLMResponse) -> ProcessingResult:
        """Handle parameter change requests with comprehensive validation"""
        if not llm_response.parameter_name:
            return ProcessingResult(
                success=False,
                response="I couldn't identify which parameter you want to change. Please specify the parameter name.",
                intent='change',
                status=ProcessingStatus.VALIDATION_ERROR,
                suggestions=llm_response.suggestions or []
            )
        
        if llm_response.parameter_value is None:
            return ProcessingResult(
                success=False,
                response="I couldn't determine what value you want to set. Please specify a value.",
                intent='change',
                status=ProcessingStatus.VALIDATION_ERROR,
                parameter_name=llm_response.parameter_name
            )
        
        # Validate the parameter value
        validation_result = self._validator.validate_parameter(
            llm_response.parameter_name,
            llm_response.parameter_value
        )
        
        if not validation_result.valid:
            error_response = f"Validation failed: {validation_result.message}"
            
            # Add suggestion if available
            if validation_result.suggested_value is not None:
                error_response += f"\nSuggested value: {validation_result.suggested_value}"
            
            return ProcessingResult(
                success=False,
                response=error_response,
                intent='change',
                status=ProcessingStatus.VALIDATION_ERROR,
                parameter_name=llm_response.parameter_name,
                parameter_value=llm_response.parameter_value
            )
        
        # Get parameter info for confirmation message
        param_info = self._validator.get_parameter_info(llm_response.parameter_name)
        
        # Build confirmation message
        confirmation_message = self._build_change_confirmation_message(
            llm_response, validation_result, param_info
        )
        
        return ProcessingResult(
            success=True,
            response=confirmation_message,
            intent='change',
            status=ProcessingStatus.SUCCESS,
            parameter_name=llm_response.parameter_name,
            parameter_value=validation_result.converted_value,
            parameter_info=param_info,
            requires_confirmation=True,
            confidence=llm_response.confidence
        )
    
    def _build_change_confirmation_message(self, llm_response: LLMResponse, 
                                         validation_result: ValidationResult, 
                                         param_info: Optional[Dict[str, Any]]) -> str:
        """Build confirmation message for parameter changes"""
        message_parts = []
        
        # Add LLM explanation if available
        if llm_response.explanation and llm_response.explanation.strip():
            message_parts.append(llm_response.explanation.strip())
        
        # Add change summary
        current_value = param_info.get('default', 'current') if param_info else 'current'
        change_summary = (f"Ready to change {llm_response.parameter_name} "
                         f"from {current_value} to {validation_result.converted_value}")
        
        # Add unit if available
        if param_info and param_info.get('unit'):
            change_summary += f" {param_info['unit']}"
        
        message_parts.append(change_summary)
        message_parts.append("Please confirm you want to apply this change to the drone.")
        
        return "\n\n".join(message_parts)
    
    def _handle_unknown_intent(self, llm_response: LLMResponse) -> ProcessingResult:
        """Handle unknown intents with helpful suggestions"""
        # Use LLM's suggestions if available, otherwise generate them
        suggestions = llm_response.suggestions or []
        
        if llm_response.parameter_name and not suggestions:
            suggestions = self._validator.get_similar_parameters(llm_response.parameter_name)
        
        response = llm_response.explanation or "I'm not sure how to help with that request."
        response += "\n\nTry asking me to 'explain' a parameter or 'change' it to a specific value."
        
        if suggestions:
            response += f"\n\nDid you mean one of these parameters: {', '.join(suggestions[:3])}?"
        
        return ProcessingResult(
            success=False,
            response=response,
            intent='unknown',
            status=ProcessingStatus.UNKNOWN_INTENT,
            parameter_name=llm_response.parameter_name,
            suggestions=suggestions,
            confidence=llm_response.confidence
        )
    
    # Utility methods for external use
    def get_available_parameters(self) -> set:
        """Get all available parameter names"""
        return self._validator.available_parameters
    
    def get_parameter_info(self, param_name: str) -> Optional[Dict[str, Any]]:
        """Get detailed parameter information"""
        return self._validator.get_parameter_info(param_name)
    
    def validate_parameter_value(self, param_name: str, value: Any) -> ValidationResult:
        """Validate a parameter value"""
        return self._validator.validate_parameter(param_name, value)
    
    def get_system_status(self) -> Dict[str, Any]:
        """Get system status information"""
        return {
            'parameter_count': self._validator.parameter_count,
            'llm_model': self._config.get('llm_model', 'gpt-4'),
            'components_initialized': True,
            'cache_info': {
                'process_user_message': self._process_user_message_cached.cache_info()._asdict()
            }
        }