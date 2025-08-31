import json
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from functools import lru_cache
import re
import os
from pathlib import Path

from openai import OpenAI

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class LLMResponse:
    intent: str
    parameter_name: Optional[str] = None
    parameter_value: Optional[float] = None
    explanation: Optional[str] = None
    confidence: float = 0.0
    suggestions: Optional[List[str]] = None

class LLMHandler:
    __slots__ = ['client', 'model', '_px4_params', '_param_names', '_system_prompt']
    
    def __init__(self, api_key: str, model: str = "gpt-4.1-mini", px4_params_path: str = 'data/px4_params.json'):
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self._px4_params = self._load_px4_params(px4_params_path)
        self._param_names = self._extract_param_names()
        self._system_prompt = self._build_system_prompt()
        logger.info(f"Loaded {len(self._param_names)} parameters")
    
    def _load_px4_params(self, params_path: str) -> List[Dict[str, Any]]:
        """Load PX4 parameters with better error handling and path resolution"""
        try:
            # Resolve absolute path
            if not os.path.isabs(params_path):
                base_dir = Path(__file__).parent.parent
                params_path = str(base_dir / params_path)
            
            logger.info(f"Loading parameters from: {params_path}")
            
            if not os.path.exists(params_path):
                logger.error(f"Parameters file not found: {params_path}")
                return []
            
            with open(params_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Handle different JSON structures
            if isinstance(data, dict) and 'parameters' in data:
                params = data['parameters']
            elif isinstance(data, list):
                params = data
            else:
                logger.error(f"Invalid PX4 parameters format in {params_path}")
                return []
            
            logger.info(f"Successfully loaded {len(params)} parameters")
            return params
                
        except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.error(f"Failed to load PX4 parameters from {params_path}: {e}")
            return []
    
    def _extract_param_names(self) -> frozenset:
        """Extract all parameter names from loaded parameters"""
        param_names = set()
        for param in self._px4_params:
            name = param.get('name')
            if name and isinstance(name, str):
                param_names.add(name)
        
        logger.info(f"Extracted {len(param_names)} unique parameter names")
        return frozenset(param_names)
    
    def _build_system_prompt(self) -> str:
        """Build comprehensive system prompt for natural conversation"""
        if not self._px4_params:
            return self._get_fallback_system_prompt()
        
        # Create a sample of parameters for context
        param_samples = []
        for param in self._px4_params[:100]:  # Increased sample size
            name = param.get('name', '')
            desc = param.get('shortDesc', param.get('longDesc', param.get('description', '')))[:120]
            if name and desc:
                param_samples.append(f"{name}: {desc}")
        
        param_context = '\n'.join(param_samples[:50])  # Show first 50
        
        return f"""You are a PX4 drone parameter expert assistant. Handle natural conversations about drone parameters.

AVAILABLE PARAMETERS (sample of {len(self._param_names)} total):
{param_context}

COMMON PARAMETER CATEGORIES:
- RC parameters (RC_*): Remote control settings
- MC parameters (MC_*): Multicopter settings  
- FW parameters (FW_*): Fixed-wing settings
- EKF2 parameters (EKF2_*): Estimation settings
- COM parameters (COM_*): Commander settings
- BAT parameters (BAT_*): Battery settings

CAPABILITIES:
- Explain what parameters do and how they affect flight
- Help users change parameter values with validation
- Handle conversational queries like "the drone feels sluggish" or "increase responsiveness"
- Map colloquial terms to actual parameter names (e.g., "roll rate" → "MC_ROLLRATE_P")
- Provide parameter suggestions for partial/unclear references

RESPONSE FORMAT (always JSON):
{{
  "intent": "explain|change|unknown|error",
  "parameter_name": "EXACT_PARAM_NAME or null",
  "parameter_value": numeric_value_or_null,
  "explanation": "Clear explanation in natural language",
  "confidence": 0.0-1.0,
  "suggestions": ["param1", "param2"] // if parameter unclear
}}

GUIDELINES:
- For vague queries like "drone is unstable", ask clarifying questions
- For parameter changes, validate ranges and provide warnings
- Be conversational and helpful, not robotic
- If unsure about parameter name, provide suggestions array
- Remember: RC_PAYLOAD_TH exists and controls RC payload threshold"""
    
    @staticmethod
    def _get_fallback_system_prompt() -> str:
        """Fallback when parameters unavailable"""
        return """You are a PX4 drone parameter expert. Handle natural conversations about drone parameters.
Respond in JSON format with: intent, parameter_name, parameter_value, explanation, confidence, suggestions."""
    
    def process_query(self, user_query: str, conversation_history: Optional[List[Dict]] = None) -> LLMResponse:
        """Process user query with optional conversation context"""
        if not user_query or not user_query.strip():
            return LLMResponse(
                intent="error", 
                explanation="Please provide a question or request about drone parameters."
            )
        
        try:
            # Build messages with conversation history if provided
            messages = [{"role": "system", "content": self._system_prompt}]
            
            # Add conversation history for context
            if conversation_history:
                messages.extend(conversation_history[-6:])  # Keep last 6 exchanges for context
            
            messages.append({"role": "user", "content": user_query.strip()})
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.1,
                max_tokens=800,
                timeout=30,
                response_format={"type": "json_object"}
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
                explanation="Sorry, I encountered an error processing your request. Please try again.",
                confidence=0.0
            )
    
    def _parse_llm_response(self, content: str) -> LLMResponse:
        """Parse and validate LLM JSON response"""
        try:
            data = json.loads(content)
            
            # Validate and clean intent
            intent = data.get('intent', 'unknown').lower()
            if intent not in {'explain', 'change', 'error', 'unknown'}:
                logger.warning(f"Unexpected intent: {intent}")
                intent = 'unknown'
            
            # Validate parameter_value
            param_value = data.get('parameter_value')
            if param_value is not None:
                try:
                    param_value = float(param_value)
                except (ValueError, TypeError):
                    logger.warning(f"Invalid parameter_value: {param_value}")
                    param_value = None
            
            # Validate confidence
            confidence = max(0.0, min(1.0, float(data.get('confidence', 0.0))))
            
            # Validate parameter name exists
            param_name = data.get('parameter_name')
            if param_name:
                # Clean up parameter name (remove quotes, spaces, etc.)
                param_name = self._clean_parameter_name(param_name)
                
                if param_name not in self._param_names:
                    # Try to find close matches
                    suggestions = self._find_similar_parameters(param_name)
                    return LLMResponse(
                        intent="unknown",
                        parameter_name=None,
                        explanation=f"Parameter '{param_name}' not found. Did you mean one of these?",
                        suggestions=suggestions,
                        confidence=0.5
                    )
            
            return LLMResponse(
                intent=intent,
                parameter_name=param_name,
                parameter_value=param_value,
                explanation=data.get('explanation', '').strip(),
                confidence=confidence,
                suggestions=data.get('suggestions', [])
            )
            
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            logger.error(f"Failed to parse LLM response: {e}. Content: {content[:200]}...")
            return LLMResponse(
                intent="error", 
                explanation="Failed to understand the response. Please try rephrasing your question.",
                confidence=0.0
            )
    
    def _clean_parameter_name(self, param_name: str) -> str:
        """Clean up parameter name by removing unwanted characters"""
        if not param_name:
            return ""
        
        # Remove quotes, extra spaces, etc.
        cleaned = param_name.strip().replace('"', '').replace("'", "").strip()
        
        # Convert to uppercase to match PX4 parameter convention
        return cleaned.upper()
    
    def _find_similar_parameters(self, param_name: str, max_suggestions: int = 5) -> List[str]:
        """Find parameters similar to the given name using multiple strategies"""
        if not param_name:
            return []
        
        param_name_upper = param_name.upper()
        suggestions = set()
        
        # Strategy 1: Exact substring matches (case-insensitive)
        for name in self._param_names:
            if param_name_upper in name.upper():
                suggestions.add(name)
                if len(suggestions) >= max_suggestions:
                    break
        
        # Strategy 2: Prefix matches
        if len(suggestions) < max_suggestions:
            for name in self._param_names:
                if name.upper().startswith(param_name_upper):
                    suggestions.add(name)
                    if len(suggestions) >= max_suggestions:
                        break
        
        # Strategy 3: Word boundary matches
        if len(suggestions) < max_suggestions:
            for name in self._param_names:
                # Split by underscores and check each part
                parts = name.upper().split('_')
                if any(param_name_upper in part for part in parts):
                    suggestions.add(name)
                    if len(suggestions) >= max_suggestions:
                        break
        
        return list(suggestions)[:max_suggestions]
    
    def validate_parameter(self, param_name: str) -> bool:
        """Check if parameter name exists"""
        return param_name in self._param_names
    
    @property
    def available_parameters(self) -> frozenset:
        """Get available parameter names"""
        return self._param_names
    
    def get_parameter_info(self, param_name: str) -> Optional[Dict[str, Any]]:
        """Get detailed info about a specific parameter"""
        for param in self._px4_params:
            if param.get('name') == param_name:
                return param
        return None
    
    def debug_parameter_lookup(self, search_term: str):
        """Debug method to check parameter lookup"""
        logger.info(f"Looking for: {search_term}")
        logger.info(f"Total parameters: {len(self._param_names)}")
        
        if search_term in self._param_names:
            logger.info(f"Exact match found: {search_term}")
            return True
        
        similar = self._find_similar_parameters(search_term, 10)
        logger.info(f"Similar parameters: {similar}")
        
        return False