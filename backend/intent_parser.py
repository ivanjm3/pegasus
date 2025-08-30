import re
import json
from typing import Dict, Any, Optional, Set, Pattern, List
from enum import Enum
from functools import lru_cache
import logging

logger = logging.getLogger(__name__)

class IntentType(Enum):
    EXPLAIN = "explain"
    CHANGE = "change"
    UNKNOWN = "unknown"
    ERROR = "error"

class IntentParser:
    __slots__ = ['_px4_params', '_param_names_lower', '_param_names_upper', 
                 '_explain_patterns', '_change_patterns', '_param_patterns']
    
    def __init__(self, px4_params_path: str = 'data/px4_params.json'):
        """Initialize with compiled patterns for better performance"""
        self._px4_params = self._load_px4_params(px4_params_path)
        self._param_names_lower = frozenset(param['name'].lower() for param in self._px4_params)
        self._param_names_upper = frozenset(param['name'].upper() for param in self._px4_params)
        
        # Pre-compile regex patterns for better performance
        self._explain_patterns = self._compile_patterns([
            r'\bwhat\s+(?:is|does|are)\b',
            r'\bexplain\b',
            r'\btell\s+me\s+about\b',
            r'\bhow\s+does\s+\w+\s+work\b',
            r'\bmeaning\s+of\b',
            r'\bdescribe\b',
            r'\bwhy\s+is\b',
            r'\bhelp\s+me\s+understand\b'
        ])
        
        self._change_patterns = self._compile_patterns([
            r'\bset\s+\w+\s+to\b',
            r'\bchange\s+\w+\s+to\b',
            r'\bincrease\b',
            r'\bdecrease\b',
            r'\badjust\b',
            r'\bmodify\b',
            r'\bupdate\b',
            r'\bconfigure\b',
            r'=\s*[-+]?\d*\.?\d+',  # Assignment pattern: param = value
            r'\bto\s+[-+]?\d*\.?\d+\b'  # "to value" pattern
        ])
        
        # Patterns for parameter extraction
        self._param_patterns = self._compile_patterns([
            r'\b([A-Z_][A-Z0-9_]{2,})\b',  # UPPERCASE_PARAMS (min 3 chars)
            r'\bparameter\s+([A-Z_][A-Z0-9_]+)\b',
            r'\bparam\s+([A-Z_][A-Z0-9_]+)\b',
            r'\b([A-Z_][A-Z0-9_]+)\s*[=:]',  # Parameter with assignment
        ])
    
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
                
        except (FileNotFoundError, json.JSONDecodeError, PermissionError) as e:
            logger.error(f"Failed to load PX4 parameters from {params_path}: {e}")
            return []
    
    @staticmethod
    def _compile_patterns(patterns: list) -> list:
        """Compile regex patterns for better performance"""
        compiled = []
        for pattern in patterns:
            try:
                compiled.append(re.compile(pattern, re.IGNORECASE))
            except re.error as e:
                logger.warning(f"Failed to compile pattern '{pattern}': {e}")
        return compiled
    
    @lru_cache(maxsize=128)  # Cache recent queries for repeated requests
    def pre_classify_intent(self, user_query: str) -> IntentType:
        """Quick intent classification with caching"""
        if not user_query or not user_query.strip():
            return IntentType.ERROR
        
        query_clean = user_query.strip()
        
        # Check for change patterns first (more specific)
        for pattern in self._change_patterns:
            if pattern.search(query_clean):
                return IntentType.CHANGE
        
        # Check for explanation patterns
        for pattern in self._explain_patterns:
            if pattern.search(query_clean):
                return IntentType.EXPLAIN
        
        # If contains parameter name + question words, likely explanation
        if self._contains_parameter(query_clean) and self._has_question_indicators(query_clean):
            return IntentType.EXPLAIN
        
        return IntentType.UNKNOWN
    
    def _contains_parameter(self, query: str) -> bool:
        """Check if query contains any known parameter name"""
        query_upper = query.upper()
        # Use set intersection for O(1) average lookup
        query_words = set(re.findall(r'\b[A-Z_][A-Z0-9_]+\b', query_upper))
        return bool(query_words & self._param_names_upper)
    
    @staticmethod
    @lru_cache(maxsize=64)
    def _has_question_indicators(query: str) -> bool:
        """Check for question indicators"""
        question_words = {'what', 'why', 'how', 'when', 'where', 'which', 'who'}
        query_lower = query.lower()
        return (query.endswith('?') or 
                any(word in query_lower for word in question_words))
    
    def extract_parameter_name(self, user_query: str) -> Optional[str]:
        """Extract parameter name with improved accuracy"""
        if not user_query:
            return None
        
        query_clean = user_query.strip()
        
        # First, try exact matches with known parameter names (case insensitive)
        query_upper = query_clean.upper()
        for param_name in self._param_names_upper:
            if param_name in query_upper:
                # Ensure it's a word boundary match, not substring
                if re.search(rf'\b{re.escape(param_name)}\b', query_upper):
                    return param_name
        
        # Then try pattern-based extraction
        for pattern in self._param_patterns:
            match = pattern.search(query_clean)
            if match:
                candidate = match.group(1).upper()
                if candidate in self._param_names_upper:
                    return candidate
        
        return None
    
    def validate_llm_response(self, llm_response: Dict[str, Any]) -> bool:
        """Comprehensive LLM response validation"""
        if not isinstance(llm_response, dict):
            return False
        
        # Check required fields
        intent = llm_response.get('intent')
        if not intent or not isinstance(intent, str):
            return False
        
        # Validate intent value
        try:
            IntentType(intent)
        except ValueError:
            logger.warning(f"Invalid intent type: {intent}")
            return False
        
        # For change intents, parameter_value is required
        if intent == IntentType.CHANGE.value:
            param_value = llm_response.get('parameter_value')
            if param_value is None:
                return False
            # Validate it's a number
            try:
                float(param_value)
            except (ValueError, TypeError):
                return False
        
        # Parameter name validation
        param_name = llm_response.get('parameter_name')
        if not param_name or not isinstance(param_name, str):
            return False
        
        # Check if parameter exists (case insensitive)
        if param_name.upper() not in self._param_names_upper:
            logger.warning(f"Unknown parameter: {param_name}")
            return False
        
        # Validate confidence if present
        confidence = llm_response.get('confidence')
        if confidence is not None:
            try:
                conf_val = float(confidence)
                if not (0.0 <= conf_val <= 1.0):
                    return False
            except (ValueError, TypeError):
                return False
        
        return True
    
    def get_parameter_suggestions(self, partial_name: str, max_suggestions: int = 5) -> List[str]:
        """Get parameter name suggestions for partial matches"""
        if not partial_name:
            return []
        
        partial_upper = partial_name.upper()
        suggestions = []
        
        for param_name in self._param_names_upper:
            if param_name.startswith(partial_upper):
                suggestions.append(param_name)
                if len(suggestions) >= max_suggestions:
                    break
        
        return suggestions
    
    @property
    def parameter_count(self) -> int:
        """Get total number of loaded parameters"""
        return len(self._param_names_upper)
    
    def is_parameter_valid(self, param_name: str) -> bool:
        """Check if parameter name is valid"""
        return param_name.upper() in self._param_names_upper if param_name else False