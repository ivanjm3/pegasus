import json
from typing import Dict, Any, Optional, Union, Set, List
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
import logging
import re
import os

logger = logging.getLogger(__name__)

class ParameterType(Enum):
    """Enum for parameter types"""
    FLOAT = "FLOAT"
    INT32 = "INT32"
    BOOL = "BOOL"
    STRING = "STRING"

@dataclass(frozen=True)
class ValidationResult:
    """Immutable validation result"""
    valid: bool
    message: str
    converted_value: Optional[Union[int, float, bool, str]] = None
    suggested_value: Optional[Union[int, float]] = None
    
class ParameterValidator:
    __slots__ = ['_param_dict', '_param_names', '_type_converters', '_bool_values']
    
    def __init__(self, px4_params_path: str = 'data/px4_params.json'):
        """Initialize with optimized data structures"""
        self._param_dict = self._load_and_index_params(px4_params_path)
        self._param_names = frozenset(self._param_dict.keys())
        
        # Pre-define type converters for efficiency
        self._type_converters = {
            ParameterType.FLOAT: self._convert_to_float,
            ParameterType.INT32: self._convert_to_int,
            ParameterType.BOOL: self._convert_to_bool,
            ParameterType.STRING: self._convert_to_string
        }
        
        # Boolean value mappings for flexible parsing
        self._bool_values = {
            # True values
            frozenset({'true', '1', 'yes', 'on', 'enabled', 'enable'}): True,
            # False values  
            frozenset({'false', '0', 'no', 'off', 'disabled', 'disable'}): False
        }
    
    def _load_and_index_params(self, params_path: str) -> Dict[str, Dict[str, Any]]:
        """Load and create optimized parameter index - handle nested 'parameters' key"""
        try:
            # Handle relative paths
            if not os.path.isabs(params_path):
                params_path = os.path.join(os.path.dirname(__file__), '..', params_path)
                params_path = os.path.abspath(params_path)
            
            with open(params_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Handle both formats: list of params or {"parameters": [...]}
            if isinstance(data, dict) and 'parameters' in data:
                px4_params = data['parameters']
            elif isinstance(data, list):
                px4_params = data
            else:
                logger.error(f"Invalid PX4 parameters format in {params_path}")
                return {}
            
            if not isinstance(px4_params, list):
                raise ValueError("Expected list of parameters")
            
            # Create case-insensitive index with validation
            param_dict = {}
            for param in px4_params:
                if not isinstance(param, dict) or 'name' not in param:
                    logger.warning(f"Invalid parameter entry: {param}")
                    continue
                
                name = param['name'].upper()
                # Validate and normalize parameter info
                param_dict[name] = self._normalize_param_info(param)
            
            logger.info(f"Loaded {len(param_dict)} parameters")
            return param_dict
            
        except (FileNotFoundError, json.JSONDecodeError, PermissionError) as e:
            logger.error(f"Failed to load parameters from {params_path}: {e}")
            return {}
    
    @staticmethod
    def _normalize_param_info(param: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize and validate parameter information"""
        normalized = {
            'name': param['name'].upper(),
            'type': param.get('type', 'FLOAT').upper(),
            'description': param.get('shortDesc', param.get('description', '')).strip(),
            'unit': param.get('units', param.get('unit', '')).strip(),
            'default': param.get('default'),
            'min': param.get('min'),
            'max': param.get('max'),
            'enum_values': param.get('enum_values', []),
            'increment': param.get('increment'),
            'decimal_places': param.get('decimal_places', 2),
            'long_description': param.get('longDesc', ''),
            'category': param.get('category', ''),
            'group': param.get('group', '')
        }
        
        # Convert min/max to appropriate types
        param_type = normalized['type']
        if param_type in ('FLOAT', 'INT32'):
            for key in ('min', 'max', 'default', 'increment'):
                if normalized[key] is not None:
                    try:
                        normalized[key] = float(normalized[key]) if param_type == 'FLOAT' else int(normalized[key])
                    except (ValueError, TypeError):
                        logger.warning(f"Invalid {key} value for {normalized['name']}")
                        normalized[key] = None
        
        return normalized
    
    @lru_cache(maxsize=256)
    def validate_parameter(self, param_name: str, value: Any) -> ValidationResult:
        """Validate parameter with caching and comprehensive checks"""
        if not param_name:
            return ValidationResult(False, "Parameter name cannot be empty")
        
        param_name_upper = param_name.upper()
        
        # Check if parameter exists
        if param_name_upper not in self._param_dict:
            suggestions = self.get_similar_parameters(param_name_upper)
            suggestion_msg = f" Did you mean: {', '.join(suggestions[:3])}?" if suggestions else ""
            return ValidationResult(
                False, 
                f"Parameter '{param_name}' not found in PX4 parameters.{suggestion_msg}"
            )
        
        param_info = self._param_dict[param_name_upper]
        
        # Get parameter type
        try:
            param_type = ParameterType(param_info['type'])
        except ValueError:
            param_type = ParameterType.FLOAT  # Default fallback
        
        # Type conversion and validation
        try:
            converted_value = self._type_converters[param_type](value)
        except (ValueError, TypeError) as e:
            return ValidationResult(
                False,
                f"Invalid value type for {param_name}. Expected {param_type.value}: {str(e)}"
            )
        
        # Range validation for numeric types
        if param_type in (ParameterType.FLOAT, ParameterType.INT32):
            range_result = self._validate_numeric_range(param_info, converted_value, param_name)
            if not range_result.valid:
                return range_result
        
        # Enum validation
        if param_info['enum_values']:
            if converted_value not in param_info['enum_values']:
                return ValidationResult(
                    False,
                    f"Value {converted_value} not in allowed values {param_info['enum_values']} for {param_name}"
                )
        
        # Increment validation for numeric types
        if param_type in (ParameterType.FLOAT, ParameterType.INT32) and param_info.get('increment'):
            increment_result = self._validate_increment(param_info, converted_value, param_name)
            if not increment_result.valid:
                return increment_result
        
        return ValidationResult(
            True,
            f"Valid value for {param_name}",
            converted_value
        )
    
    def _validate_numeric_range(self, param_info: Dict[str, Any], value: Union[int, float], param_name: str) -> ValidationResult:
        """Validate numeric value against min/max constraints"""
        min_val = param_info.get('min')
        max_val = param_info.get('max')
        
        if min_val is not None and value < min_val:
            suggested = max(min_val, value)  # Suggest the minimum
            return ValidationResult(
                False,
                f"Value {value} below minimum {min_val} for {param_name}",
                suggested_value=suggested
            )
        
        if max_val is not None and value > max_val:
            suggested = min(max_val, value)  # Suggest the maximum
            return ValidationResult(
                False,
                f"Value {value} above maximum {max_val} for {param_name}",
                suggested_value=suggested
            )
        
        return ValidationResult(True, "Range validation passed", value)
    
    def _validate_increment(self, param_info: Dict[str, Any], value: Union[int, float], param_name: str) -> ValidationResult:
        """Validate value follows increment constraints"""
        increment = param_info['increment']
        default = param_info.get('default', 0)
        
        # Check if value is a valid increment from default
        diff = abs(value - default)
        if increment > 0 and diff % increment != 0:
            # Suggest nearest valid value
            steps = round(diff / increment)
            suggested = default + (steps * increment * (1 if value > default else -1))
            return ValidationResult(
                False,
                f"Value {value} doesn't match increment {increment} for {param_name}",
                suggested_value=suggested
            )
        
        return ValidationResult(True, "Increment validation passed", value)
    
    def _convert_to_float(self, value: Any) -> float:
        """Convert value to float with comprehensive parsing"""
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            # Handle scientific notation and special cases
            value = value.strip().lower()
            if value in ('inf', 'infinity'):
                return float('inf')
            if value in ('-inf', '-infinity'):
                return float('-inf')
            return float(value)
        raise ValueError(f"Cannot convert {type(value).__name__} to float")
    
    def _convert_to_int(self, value: Any) -> int:
        """Convert value to int with validation"""
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            if value.is_integer():
                return int(value)
            raise ValueError("Float value is not an integer")
        if isinstance(value, str):
            value = value.strip()
            # Handle hex, octal, binary
            if value.startswith(('0x', '0X')):
                return int(value, 16)
            elif value.startswith(('0o', '0O')):
                return int(value, 8)
            elif value.startswith(('0b', '0B')):
                return int(value, 2)
            return int(float(value))  # Handle "1.0" -> 1
        raise ValueError(f"Cannot convert {type(value).__name__} to int")
    
    def _convert_to_bool(self, value: Any) -> bool:
        """Convert value to bool with flexible parsing"""
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            value_lower = value.strip().lower()
            for true_values, result in self._bool_values.items():
                if value_lower in true_values:
                    return result
            raise ValueError(f"Cannot parse '{value}' as boolean")
        raise ValueError(f"Cannot convert {type(value).__name__} to bool")
    
    @staticmethod
    def _convert_to_string(value: Any) -> str:
        """Convert value to string"""
        return str(value)
    
    def get_similar_parameters(self, param_name: str, max_suggestions: int = 5) -> List[str]:
        """Find similar parameter names using simple string matching"""
        suggestions = []
        param_name_lower = param_name.lower()
        
        # Exact substring matches first
        for name in self._param_names:
            if param_name_lower in name.lower():
                suggestions.append(name)
                if len(suggestions) >= max_suggestions:
                    break
        
        # If not enough, try prefix matches
        if len(suggestions) < max_suggestions:
            for name in self._param_names:
                if name.lower().startswith(param_name_lower) and name not in suggestions:
                    suggestions.append(name)
                    if len(suggestions) >= max_suggestions:
                        break
        
        return suggestions
    
    def get_parameter_info(self, param_name: str) -> Optional[Dict[str, Any]]:
        """Get detailed parameter information"""
        if not param_name:
            return None
        return self._param_dict.get(param_name.upper())
    
    def get_parameter_summary(self, param_name: str) -> Optional[str]:
        """Get human-readable parameter summary"""
        param_info = self.get_parameter_info(param_name)
        if not param_info:
            return None
        
        summary_parts = [f"Parameter: {param_info['name']}"]
        
        if param_info['description']:
            summary_parts.append(f"Description: {param_info['description']}")
        
        summary_parts.append(f"Type: {param_info['type']}")
        
        if param_info.get('min') is not None or param_info.get('max') is not None:
            min_val = param_info.get('min', 'N/A')
            max_val = param_info.get('max', 'N/A')
            summary_parts.append(f"Range: {min_val} to {max_val}")
        
        if param_info.get('unit'):
            summary_parts.append(f"Unit: {param_info['unit']}")
        
        if param_info.get('default') is not None:
            summary_parts.append(f"Default: {param_info['default']}")
        
        if param_info.get('enum_values'):
            summary_parts.append(f"Allowed values: {', '.join(map(str, param_info['enum_values']))}")
        
        return " | ".join(summary_parts)
    
    def validate_multiple_parameters(self, param_values: Dict[str, Any]) -> Dict[str, ValidationResult]:
        """Validate multiple parameters efficiently"""
        results = {}
        for param_name, value in param_values.items():
            results[param_name] = self.validate_parameter(param_name, value)
        return results
    
    @property
    def parameter_count(self) -> int:
        """Get total number of parameters"""
        return len(self._param_names)
    
    def is_valid_parameter(self, parameter_name: str) -> bool:
        """Check if a parameter exists in the parameter database."""
        return parameter_name.upper() in self._param_names
    
    @property
    def available_parameters(self) -> Set[str]:
        """Get set of all available parameter names"""
        return self._param_names
    
    def get_parameters_by_type(self, param_type: Union[str, ParameterType]) -> List[str]:
        """Get all parameters of a specific type"""
        if isinstance(param_type, str):
            param_type = param_type.upper()
        else:
            param_type = param_type.value
        
        return [name for name, info in self._param_dict.items() 
                if info['type'] == param_type]