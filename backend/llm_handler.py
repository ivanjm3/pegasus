import json
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from functools import lru_cache
import re

from openai import OpenAI

logger = logging.getLogger(__name__)

@dataclass(frozen=True, slots=True)
class LLMResponse:
    intent: str
    parameter_name: Optional[str] = None
    parameter_value: Optional[float] = None
    explanation: Optional[str] = None
    confidence: float = 0.0

class LLMHandler:
    __slots__ = ['client', 'model', '_px4_params', '_param_names', '_system_prompt']
    
    def __init__(self, api_key: str, model: str = "gpt-4", px4_params_path: str = 'data/px4_params.json'):
        """Initialize with dependency injection for better testability"""
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self._px4_params = self._load_px4_params(px4_params_path)
        self._param_names = frozenset(param['name'] for param in self._px4_params)
        self._system_prompt = self._build_system_prompt()
    
    @staticmethod
    def _load_px4_params(params_path: str) -> List[Dict[str, Any]]:
        """Load PX4 parameters with error handling - handle nested 'parameters' key"""
        try:
            with open(params_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Handle both formats: list of params or {"parameters": [...]}
            if isinstance(data, dict) and 'parameters' in data:
                return data['parameters']
            elif isinstance(data, list):
                return data
            else:
                logger.error(f"Invalid PX4 parameters format in {params_path}")
                return []
                
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.error(f"Failed to load PX4 parameters from {params_path}: {e}")
            return []
    
    def _build_system_prompt(self) -> str:
        """Build system prompt with PX4 parameter context (cached)"""
        if not self._px4_params:
            return self._get_fallback_system_prompt()
        
        # Use a more efficient string join
        param_list = ', '.join(self._param_names)
        
        return f"""You are a PX4 drone parameter expert. Your role is to:
1. Explain drone parameters when users ask about them
2. Help users change parameters with valid values

Available PX4 parameters: {param_list}

Always respond in JSON format with:
- intent: "explain" or "change"
- parameter_name: the parameter being discussed
- parameter_value: only if changing a parameter (must be valid)
- explanation: clear explanation of the parameter
- confidence: 0.0 to 1.0 confidence in your response

For parameter changes, validate that values are within acceptable ranges."""
    
    @staticmethod
    def _get_fallback_system_prompt() -> str:
        """Fallback system prompt when PX4 params are unavailable"""
        return """You are a PX4 drone parameter expert. Respond in JSON format with:
- intent: "explain" or "change"
- parameter_name: the parameter being discussed
- parameter_value: only if changing a parameter
- explanation: clear explanation
- confidence: 0.0 to 1.0 confidence"""
    
    def process_query(self, user_query: str) -> LLMResponse:
        """Process user query through LLM with improved error handling"""
        if not user_query or not user_query.strip():
            return LLMResponse(
                intent="error", 
                explanation="Empty query provided."
            )
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self._system_prompt},
                    {"role": "user", "content": user_query.strip()}
                ],
                temperature=0.1,
                max_tokens=500,
                timeout=30  # Add timeout
            )
            
            content = response.choices[0].message.content
            if not content:
                return LLMResponse(
                    intent="error", 
                    explanation="No response received from AI."
                )
            
            return self._parse_llm_response(content)
            
        except Exception as e:
            logger.error(f"LLM processing error: {e}")
            return LLMResponse(
                intent="error", 
                explanation="Sorry, I encountered an error processing your request.",
                confidence=0.0
            )
    
    def _parse_llm_response(self, content: str) -> LLMResponse:
        """Parse LLM response with improved JSON extraction"""
        try:
            # More robust JSON extraction using regex
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if not json_match:
                raise ValueError("No JSON found in response")
            
            data = json.loads(json_match.group())
            
            # Validate required fields
            intent = data.get('intent', 'unknown')
            if intent not in {'explain', 'change', 'error', 'unknown'}:
                logger.warning(f"Unexpected intent: {intent}")
            
            # Validate parameter_value is numeric if present
            param_value = data.get('parameter_value')
            if param_value is not None:
                try:
                    param_value = float(param_value)
                except (ValueError, TypeError):
                    logger.warning(f"Invalid parameter_value: {param_value}")
                    param_value = None
            
            # Validate confidence is in range [0, 1]
            confidence = max(0.0, min(1.0, float(data.get('confidence', 0.0))))
            
            return LLMResponse(
                intent=intent,
                parameter_name=data.get('parameter_name'),
                parameter_value=param_value,
                explanation=data.get('explanation', '').strip(),
                confidence=confidence
            )
            
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            logger.error(f"Failed to parse LLM response: {e}. Content: {content[:200]}...")
            return LLMResponse(
                intent="error", 
                explanation="Failed to parse response from AI.",
                confidence=0.0
            )
    
    def validate_parameter(self, param_name: str) -> bool:
        """Check if parameter name exists in loaded PX4 parameters"""
        return param_name in self._param_names
    
    @property
    def available_parameters(self) -> frozenset:
        """Get available parameter names"""
        return self._param_names