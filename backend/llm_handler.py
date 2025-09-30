"""
Enhanced LLM-based agent for intelligent and safe PX4 drone parameter management.
This module provides context-aware, safety-conscious natural language interaction
with drone parameters, including detailed explanations and proactive guidance.
"""

import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum

from openai import OpenAI

logger = logging.getLogger(__name__)

# Tooling - Import with proper error handling
try:
    from drone.mavlink_handler import MAVLinkHandler
    from drone.param_manager import (
        change_parameter,
        list_parameters,
        read_parameter,
        refresh_parameters,
        search_parameters,
    )
    DRONE_MODULE_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Drone module not available: {e}")
    DRONE_MODULE_AVAILABLE = False
    # Define dummy functions for when drone module is not available
    def change_parameter(*args, **kwargs):
        return "Drone module not available"
    def list_parameters(*args, **kwargs):
        return "Drone module not available"
    def read_parameter(*args, **kwargs):
        return "Drone module not available"
    def refresh_parameters(*args, **kwargs):
        return "Drone module not available"
    def search_parameters(*args, **kwargs):
        return "Drone module not available"


# --- Enums for Request Types ---

class RequestType(Enum):
    """Types of user requests the agent can handle."""
    TOOL_EXECUTION = "tool_execution"
    EXPLANATION_ONLY = "explanation_only"
    SAFETY_ANALYSIS = "safety_analysis"
    GUIDANCE = "guidance"


# --- Data Classes for Structured LLM Responses ---

@dataclass(frozen=True)
class SafetyAnalysis:
    """Safety assessment of a parameter change."""
    is_safe: bool
    risk_level: str  # "safe", "caution", "dangerous", "critical"
    risks: List[str]
    consequences: List[str]
    safe_alternatives: List[Dict[str, Any]]


@dataclass(frozen=True)
class LLMResponse:
    """Enhanced structured response from the LLM with safety and context awareness."""
    request_type: RequestType
    intent: str
    args: Dict[str, Any] = field(default_factory=dict)
    explanation: Optional[str] = None
    confidence: float = 0.0
    safety_analysis: Optional[SafetyAnalysis] = None
    suggestions: Optional[List[str]] = None
    context_summary: Optional[str] = None
    next_steps: Optional[List[str]] = None


# --- Conversation Context Manager ---

class ConversationContext:
    """Maintains conversation history and context for better responses."""
    
    def __init__(self, max_history: int = 10):
        self.history: List[Dict[str, Any]] = []
        self.max_history = max_history
        self.parameter_interactions: Dict[str, List[str]] = {}
        self.safety_warnings_given: List[str] = []
        self.user_preferences: Dict[str, Any] = {}
    
    def add_interaction(self, user_query: str, response: LLMResponse, result: str):
        """Records an interaction for context awareness."""
        interaction = {
            "timestamp": time.time(),
            "user_query": user_query,
            "response_type": response.request_type.value,
            "intent": response.intent,
            "result": result[:500],  # Truncate long results
            "safety_warned": response.safety_analysis is not None and not response.safety_analysis.is_safe
        }
        
        self.history.append(interaction)
        if len(self.history) > self.max_history:
            self.history.pop(0)
        
        # Track parameter-specific interactions
        if response.args and "param_name" in response.args:
            param = response.args["param_name"]
            if param not in self.parameter_interactions:
                self.parameter_interactions[param] = []
            self.parameter_interactions[param].append(user_query)
    
    def get_context_summary(self) -> str:
        """Generates a summary of recent context for the LLM."""
        if not self.history:
            return "No previous interactions in this session."
        
        recent = self.history[-3:]  # Last 3 interactions
        summary_parts = []
        
        for interaction in recent:
            summary_parts.append(
                f"- User asked: '{interaction['user_query'][:100]}' "
                f"(Type: {interaction['response_type']}, Intent: {interaction['intent']})"
            )
        
        if self.safety_warnings_given:
            summary_parts.append(f"- Safety warnings issued for: {', '.join(self.safety_warnings_given[-3:])}")
        
        return "\n".join(summary_parts)


# --- Core Enhanced LLM Handler ---

class LLMHandler:
    """Enhanced LLM handler with safety awareness and intelligent interaction."""
    
    def __init__(self, api_key: str, model: str = "gpt-4-turbo", px4_params_path: str = 'data/px4_params.json'):
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self._px4_params = self._load_px4_params(px4_params_path)
        self._param_dict = {p['name']: p for p in self._px4_params if 'name' in p}
        self._param_names = frozenset(self._param_dict.keys())
        self.context = ConversationContext()
        self._system_prompt = self._build_enhanced_system_prompt()
        logger.info(f"Enhanced LLMHandler initialized with {len(self._param_names)} parameters.")
    
    def _load_px4_params(self, params_path: str) -> List[Dict[str, Any]]:
        """Loads the PX4 parameter definitions from the JSON file."""
        try:
            base_dir = Path(__file__).parent.parent
            full_path = base_dir / params_path
            with open(full_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data.get('parameters', []) if isinstance(data, dict) else []
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.error(f"Failed to load PX4 parameters from {params_path}: {e}")
            return []
    
    def _build_enhanced_system_prompt(self) -> str:
        """Builds an enhanced, detailed system prompt for intelligent interaction."""
        return """You are an advanced, safety-conscious AI assistant for managing PX4 drone parameters. 
Your role is to intelligently interpret user requests, provide detailed explanations, ensure safety, 
and guide users through parameter management with context awareness.

## CRITICAL RESPONSIBILITIES:

### 1. REQUEST CLASSIFICATION
First, determine the type of user request:
- **TOOL_EXECUTION**: User wants to perform an action (list, search, read, change, refresh parameters)
- **EXPLANATION_ONLY**: User seeks information/explanation without executing tools
- **SAFETY_ANALYSIS**: User asks about risks, consequences, or safety of operations
- **GUIDANCE**: User needs suggestions or help deciding what to do

### 2. RESPONSE STRUCTURE
Always respond with a JSON object containing:
{{
    "request_type": "tool_execution|explanation_only|safety_analysis|guidance",
    "intent": "specific_tool_name|explain|analyze|guide",
    "args": {{"relevant_arguments"}},
    "explanation": "Detailed explanation of what you're doing and why",
    "confidence": 0.0-1.0,
    "safety_analysis": {{
        "is_safe": true/false,
        "risk_level": "safe|caution|dangerous|critical",
        "risks": ["list of specific risks"],
        "consequences": ["what could happen if executed"],
        "safe_alternatives": [{{"param": "name", "value": "safe_value", "reason": "why this is safer"}}]
    }},
    "suggestions": ["list of helpful suggestions"],
    "context_summary": "summary of relevant context from conversation",
    "next_steps": ["possible actions user could take next"]
}}

### 3. GUIDANCE FOR SCENARIO-BASED QUERIES
When the user asks scenario questions (e.g., "It's windy and I want to scan a 200m building"), do NOT ask for a specific parameter. Classify as `request_type = guidance` and:
- Provide a concise rationale in "explanation" tailored to the scenario (wind, altitude, mission type, safety).
- Populate `args.proposed_parameters` with 5-12 items, each object like: {"param": "NAME", "value": number/string, "reason": "why"}.
- Include `args.related_parameters` with 3-8 additional params to review.
- Ensure values are within typical safe ranges; note constraints if the dataset lacks exact bounds.
- Prefer well-known PX4 params for speed, accel, position control, EKF robustness, RTL/landing, and failsafes.

PX4 airframe hint: If the user mentions an airframe class (e.g., quadcopter, hexacopter, octocopter, plane, VTOL), include `SYS_AUTOSTART` in `args.proposed_parameters` with the appropriate integer airframe ID for that class, and add a note to verify the exact ID against the user’s PX4 firmware version and airframe list. For example, for a generic octocopter you may suggest `SYS_AUTOSTART = 4010 (verify in docs)`. Do not output string names for airframe; `SYS_AUTOSTART` is an integer ID.

Example for windy, tall-building mapping (adapt to airframe):
args.proposed_parameters = [
  {"param":"MPC_XY_VEL_MAX","value":8,"reason":"limit horizontal speed for stability in gusts"},
  {"param":"MPC_Z_VEL_MAX_UP","value":2,"reason":"controlled ascent near structure"},
  {"param":"MPC_Z_VEL_MAX_DN","value":1.5,"reason":"gentle descent to reduce oscillation"},
  {"param":"MPC_ACC_HOR","value":3.5,"reason":"moderate horizontal acceleration for smoother tracking"},
  {"param":"MPC_ACC_UP_MAX","value":2.5,"reason":"avoid aggressive climbs in wind"},
  {"param":"MPC_ACC_DOWN_MAX","value":1.8,"reason":"stable descents"},
  {"param":"RTL_RETURN_ALT","value":230,"reason":"clear 200m building + margin"},
  {"param":"GF_MAX_VER_DIST","value":230,"reason":"permit vertical envelope for mission"},
  {"param":"MIS_TAKEOFF_ALT","value":10,"reason":"safe takeoff altitude before approach"}
]
args.related_parameters = ["RTL_DESCEND_ALT", "EKF2_AID_MASK", "COM_OBL_ACT", "LNDMC_ALT_MAX", "MPC_POS_MODE"]

Follow-up like "apply/set these values" should switch to:
{
  "request_type": "tool_execution",
  "intent": "batch_change_parameters",
  "args": {"proposed_parameters": [{"param":"NAME","value":X}]}
}

### 4. AVAILABLE TOOLS (for TOOL_EXECUTION requests only):
- **list_parameters**: Lists all drone parameters
  Args: None
  Use when: User wants to see all available parameters

- **search_parameters**: Searches parameters by keyword
  Args: {{"search_term": "keyword"}}
  Use when: User wants to find parameters related to a topic

- **read_parameter**: Gets current value and explanation
  Args: {{"param_name": "EXACT_PARAM_NAME"}}
  Use when: User wants to know a specific parameter's value

- **change_parameter**: Modifies a parameter value
  Args: {{"param_name": "EXACT_PARAM_NAME", "new_value_str": "value"}}
  Use when: User wants to change a parameter
  CRITICAL: Always perform safety analysis before suggesting this

- **refresh_parameters**: Updates parameter list from drone
  Args: None
  Use when: User wants latest values from the drone

### 4. SAFETY PROTOCOL
For ANY parameter change request:
1. **Identify the parameter** and its valid range
2. **Analyze safety implications**:
   - What does this parameter control?
   - What are the min/max safe values?
   - What happens if set incorrectly?
   - Could this cause crashes, instability, or damage?
3. **Provide risk assessment**:
   - safe: Normal operation within recommended range
   - caution: Valid but approaching limits, monitor closely
   - dangerous: Outside normal range, could cause issues
   - critical: Will likely cause immediate failure/crash
4. **Suggest alternatives** if unsafe

### 5. INTELLIGENT PARAMETER MAPPING
When users use natural language to describe parameters:
- "horizontal speed" → MPC_VEL_MANUAL, MPC_XY_VEL_MAX
- "vertical speed" → MPC_Z_VEL_MAX_UP, MPC_Z_VEL_MAX_DN
- "acceleration" → MPC_ACC_HOR, MPC_ACC_UP_MAX, MPC_ACC_DOWN_MAX
- "battery" → BAT_* parameters
- "return to home" → RTL_* parameters
- "landing" → LNDMC_* parameters
- "takeoff" → MIS_TAKEOFF_ALT, TKO_* parameters
- "pitch/roll limits" → MC_PITCHRATE_MAX, MC_ROLLRATE_MAX
- "altitude limits" → COM_OBL_ACT, GF_MAX_VER_DIST

PX4-specific detail: Some parameters represent strings or bitmasks conceptually (e.g., airframe names, mixer filenames, aiding masks) but are implemented and transmitted as integers/bitmasks over MAVLink (which carries `float32` values). Always treat and display such parameters according to their defined type (e.g., show integers as integers, and bitmasks with decimal and hex), and never convert or coerce types when presenting values.

Persistence note: Airframe selection parameters require special handling. When setting `SYS_AUTOSTART` to an airframe ID, also set `SYS_AUTOCONFIG = 1` and reboot the autopilot to apply and persist configuration. Until reboot and re-initialization, reading back may show default/previous values (often 0). Make this clear in guidance and suggested next steps.

### 6. CONTEXT AWARENESS
- Remember previous interactions in the conversation
- If a parameter was discussed before, reference that context
- Build on previous explanations without unnecessary repetition
- Track safety warnings already given
- Learn user preferences (e.g., if they prefer metric/imperial units)

### 7. EXPLANATION REQUIREMENTS
For EXPLANATION_ONLY requests, provide:
- What the parameter does in plain language
- How it affects drone behavior
- Valid range and units
- Common use cases
- Related parameters
- Safety considerations
- Example safe values for different scenarios

### 8. VALUE VALIDATION
When validating parameter values:
- Check against min/max bounds
- Consider the parameter type (int, float, bool, enum)
- Verify units (meters, degrees, m/s, etc.)
- Check dependencies (some params affect others)
- Consider the flight mode context

### 9. ERROR HANDLING
If you cannot fulfill a request:
- NEVER just say "I can't do that"
- ALWAYS explain WHY you cannot
- Describe what WOULD happen if you could
- Suggest what CAN be done instead
- Provide educational context

### 10. RESPONSE TONE
- Be professional but approachable
- Use clear, non-technical language when possible
- Provide technical details when needed
- Be proactive with warnings and suggestions
- Encourage safe experimentation

## EXAMPLES:

**Example 1 - Unsafe change request:**
User: "Set the horizontal acceleration to 1000"
Your response should classify as TOOL_EXECUTION but with critical safety analysis, 
explaining that MPC_ACC_HOR typically ranges 2-15 m/s², 1000 would cause violent, 
uncontrollable movements, suggest 3-5 for normal use, 8-10 for aggressive flying.

**Example 2 - Vague request:**
User: "Make the drone faster"
Your response should classify as GUIDANCE, ask which aspect (horizontal speed, 
vertical speed, acceleration), explain the parameters involved, suggest safe 
incremental changes.

**Example 3 - Information request:**
User: "What would happen if I set the battery failsafe too low?"
Your response should classify as EXPLANATION_ONLY, explain BAT_CRIT_THR and 
BAT_LOW_THR parameters, describe risks (crash, battery damage), recommend safe values.

**Example 4 - Context-aware follow-up:**
User: "Actually, set it to 5 instead"
Your response should reference the previous parameter discussed, validate the 
new value in that context, execute if safe.

Remember: You are the safety guardian between the user and potentially dangerous 
drone operations. Be helpful, but prioritize safety and education."""
    
    def process_query(self, user_query: str, conversation_history: Optional[List[Dict]] = None) -> LLMResponse:
        """Processes a query with enhanced context and safety awareness."""
        if not user_query or not user_query.strip():
            return LLMResponse(
                request_type=RequestType.GUIDANCE,
                intent="error",
                explanation="Query cannot be empty. Please describe what you'd like to do with the drone parameters."
            )
        
        try:
            # Build context-aware message
            context_summary = self.context.get_context_summary()
            
            # Use provided conversation history if available, otherwise use internal context
            if conversation_history:
                messages = [{"role": "system", "content": self._system_prompt}]
                # Add conversation history
                for msg in conversation_history[-6:]:  # Last 6 messages for context
                    if msg.get("role") in ["user", "assistant"]:
                        messages.append({
                            "role": msg["role"],
                            "content": msg["content"]
                        })
                # Add current query
                messages.append({"role": "user", "content": user_query.strip()})
            else:
                # Fallback to internal context
                messages = [
                    {"role": "system", "content": self._system_prompt},
                    {"role": "user", "content": f"""
Current context from our conversation:
{context_summary}

User's current request: {user_query.strip()}

Please analyze this request considering the context above and provide a comprehensive response.
"""}
                ]
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.1,  # Low temperature for consistency
                response_format={"type": "json_object"}
            )
            
            content = response.choices[0].message.content
            llm_response = self._parse_enhanced_response(content)
            
            # Record the interaction
            self.context.add_interaction(user_query, llm_response, "")
            
            return llm_response
            
        except Exception as e:
            logger.error(f"LLM processing error: {e}")
            return LLMResponse(
                request_type=RequestType.GUIDANCE,
                intent="error",
                explanation=f"I encountered an error processing your request: {e}. Please try rephrasing or breaking down your request."
            )
    
    def _parse_enhanced_response(self, content: str) -> LLMResponse:
        """Parses the enhanced JSON response from the LLM."""
        try:
            data = json.loads(content)
            
            # Parse request type
            request_type_str = data.get('request_type', 'guidance')
            request_type = RequestType(request_type_str) if request_type_str in [rt.value for rt in RequestType] else RequestType.GUIDANCE
            
            # Parse safety analysis if present
            safety_data = data.get('safety_analysis')
            safety_analysis = None
            if safety_data:
                safety_analysis = SafetyAnalysis(
                    is_safe=safety_data.get('is_safe', True),
                    risk_level=safety_data.get('risk_level', 'safe'),
                    risks=safety_data.get('risks', []),
                    consequences=safety_data.get('consequences', []),
                    safe_alternatives=safety_data.get('safe_alternatives', [])
                )
                
                # Track safety warnings
                if not safety_analysis.is_safe:
                    param_name = data.get('args', {}).get('param_name', 'unknown')
                    self.context.safety_warnings_given.append(param_name)
            
            return LLMResponse(
                request_type=request_type,
                intent=data.get('intent', 'unknown'),
                args=data.get('args', {}),
                explanation=data.get('explanation'),
                confidence=data.get('confidence', 0.0),
                safety_analysis=safety_analysis,
                suggestions=data.get('suggestions', []),
                context_summary=data.get('context_summary'),
                next_steps=data.get('next_steps', [])
            )
            
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error(f"Failed to parse enhanced LLM response: {content}")
            return LLMResponse(
                request_type=RequestType.GUIDANCE,
                intent="error",
                explanation=f"I had trouble understanding the response format. Let me try to help you differently."
            )
    
    def get_parameter_info(self, param_name: str) -> Optional[Dict[str, Any]]:
        """Retrieves detailed information for a specific parameter."""
        return self._param_dict.get(param_name)
    
    def find_related_parameters(self, param_name: str) -> List[str]:
        """Finds parameters related to a given parameter."""
        if not param_name:
            return []
        
        # Extract prefix (e.g., "MPC" from "MPC_ACC_HOR")
        prefix = param_name.split('_')[0] if '_' in param_name else param_name[:3]
        
        related = []
        for p in self._param_names:
            if p.startswith(prefix) and p != param_name:
                related.append(p)
                if len(related) >= 5:  # Limit to 5 related params
                    break
        
        return related


# --- Enhanced Agent Executor ---

class AgentExecutor:
    """
    Enhanced orchestrator with intelligent decision-making and safety awareness.
    """
    
    def __init__(self, api_key: str, model: str = "gpt-4-turbo"):
        self.llm_handler = LLMHandler(api_key, model)
        self.mav_handler: Optional[MAVLinkHandler] = None
        self._connect_to_drone()
    
    def _connect_to_drone(self):
        """Initializes and connects the MAVLink handler."""
        try:
            self.mav_handler = MAVLinkHandler()
            logger.info("Connecting to drone...")
            if not self.mav_handler.connect():
                raise ConnectionError("MAVLink connection failed.")
            logger.info(f"Connected to {self.mav_handler.config.port}")
            print("✅ Drone Connected Successfully!")
            print("📡 Refreshing parameters from drone...")
            refresh_result = refresh_parameters(self.mav_handler)
            print(f"📊 {refresh_result}")
        except Exception as e:
            logger.error(f"Fatal error during drone connection: {e}")
            self.mav_handler = None
            print(f"❌ Error: Could not connect to drone. {e}")
            print("💡 Running in explanation-only mode (no drone connection)")
    
    def execute_task(self, user_prompt: str) -> str:
        """
        Enhanced task execution with intelligent routing and comprehensive responses.
        """
        # 1. Get enhanced response from LLM
        llm_response = self.llm_handler.process_query(user_prompt)
        
        # 2. Build initial response with explanation
        response_parts = []
        
        if llm_response.explanation:
            response_parts.append(f"📋 **Analysis**: {llm_response.explanation}\n")
        
        # 3. Handle based on request type
        if llm_response.request_type == RequestType.EXPLANATION_ONLY:
            result = self._handle_explanation_request(llm_response)
        elif llm_response.request_type == RequestType.SAFETY_ANALYSIS:
            result = self._handle_safety_analysis(llm_response)
        elif llm_response.request_type == RequestType.GUIDANCE:
            result = self._handle_guidance_request(llm_response)
        elif llm_response.request_type == RequestType.TOOL_EXECUTION:
            result = self._handle_tool_execution(llm_response)
        else:
            result = "I'm not sure how to handle that request. Could you please rephrase?"
        
        response_parts.append(result)
        
        # 4. Add suggestions and next steps
        if llm_response.suggestions:
            response_parts.append("\n💡 **Suggestions**:")
            for suggestion in llm_response.suggestions[:3]:
                response_parts.append(f"  • {suggestion}")
        
        if llm_response.next_steps:
            response_parts.append("\n🔜 **Possible next steps**:")
            for step in llm_response.next_steps[:3]:
                response_parts.append(f"  • {step}")
        
        # 5. Update context with result
        final_response = "\n".join(response_parts)
        self.llm_handler.context.add_interaction(user_prompt, llm_response, final_response)
        
        return final_response
    
    def _handle_explanation_request(self, llm_response: LLMResponse) -> str:
        """Handles explanation-only requests without executing tools."""
        args = llm_response.args or {}
        param_name = args.get('param_name')
        
        if param_name:
            param_info = self.llm_handler.get_parameter_info(param_name)
            if param_info:
                return self._format_parameter_explanation(param_name, param_info)
            else:
                # Find similar parameters
                similar = self._find_similar_parameters(param_name)
                return f"❓ Parameter '{param_name}' not found. Did you mean one of these?\n{similar}"
        
        return "📚 Please specify which parameter or topic you'd like to learn about."
    
    def _handle_safety_analysis(self, llm_response: LLMResponse) -> str:
        """Provides detailed safety analysis for operations."""
        if not llm_response.safety_analysis:
            return "⚠️ Safety analysis not available for this request."
        
        sa = llm_response.safety_analysis
        response_parts = [f"\n🛡️ **Safety Analysis** - Risk Level: {sa.risk_level.upper()}"]
        
        if sa.risks:
            response_parts.append("\n⚠️ **Potential Risks**:")
            for risk in sa.risks:
                response_parts.append(f"  • {risk}")
        
        if sa.consequences:
            response_parts.append("\n💥 **Possible Consequences**:")
            for consequence in sa.consequences:
                response_parts.append(f"  • {consequence}")
        
        if sa.safe_alternatives:
            response_parts.append("\n✅ **Safe Alternatives**:")
            for alt in sa.safe_alternatives:
                response_parts.append(f"  • Set {alt['param']} to {alt['value']}: {alt['reason']}")
        
        return "\n".join(response_parts)
    
    def _handle_guidance_request(self, llm_response: LLMResponse) -> str:
        """Provides guidance and suggestions without executing actions."""
        return f"🤔 **Guidance**: I'm here to help you understand and safely manage drone parameters."
    
    def _handle_tool_execution(self, llm_response: LLMResponse) -> str:
        """Executes tools with safety checks and comprehensive feedback."""
        if not self.mav_handler:
            return "⚠️ Cannot execute commands: Not connected to a drone. Running in explanation-only mode."
        
        intent = llm_response.intent
        args = llm_response.args or {}
        
        # Safety check for parameter changes
        if intent == "change_parameter" and llm_response.safety_analysis:
            if not llm_response.safety_analysis.is_safe:
                safety_msg = self._handle_safety_analysis(llm_response)
                return f"🛑 **CHANGE BLOCKED FOR SAFETY**\n{safety_msg}"
        
        # Route to appropriate tool
        if intent == "list_parameters":
            result = list_parameters(self.mav_handler)
        elif intent == "search_parameters":
            result = search_parameters(self.mav_handler, **args)
        elif intent == "read_parameter":
            result = self._enhanced_read_parameter(**args)
        elif intent == "refresh_parameters":
            result = refresh_parameters(self.mav_handler)
        elif intent == "change_parameter":
            result = self._enhanced_change_parameter(**args)
        elif intent == "batch_change_parameters":
            # Expect args.proposed_parameters = [{"param":"NAME","value":X}, ...]
            proposed = args.get('proposed_parameters') or []
            if not isinstance(proposed, list) or not proposed:
                return "❌ No parameters provided to change."
            success_changes = []
            failed_changes = []
            for item in proposed:
                try:
                    p = item.get('param') or item.get('name')
                    v = item.get('value') or item.get('target')
                    if not p or v is None:
                        failed_changes.append((p or 'UNKNOWN', 'missing parameter or value'))
                        continue
                    # Use enhanced change path for validation feedback
                    change_result = self._enhanced_change_parameter(param_name=p, new_value_str=str(v))
                    if change_result.startswith("✅") or "Verified change" in change_result:
                        success_changes.append((p, v))
                    else:
                        failed_changes.append((p, change_result.split("\n")[0]))
                except Exception as e:
                    failed_changes.append((str(item), str(e)))
            summary = ["🛠️ Batch Change Summary:"]
            if success_changes:
                summary.append("\n✅ Applied:")
                for p, v in success_changes[:20]:
                    summary.append(f"• {p} → {v}")
            if failed_changes:
                summary.append("\n❌ Failed:")
                for p, err in failed_changes[:20]:
                    summary.append(f"• {p}: {err}")
            result = "\n".join(summary)
        else:
            result = f"❓ Unknown intent: {intent}"
        
        return f"\n🔧 **Execution Result**:\n{result}"

    # Public helper to run a tool intent from outside this class
    def run_tool_intent(self, llm_response: LLMResponse) -> str:
        return self._handle_tool_execution(llm_response)
    
    def _enhanced_read_parameter(self, param_name: str) -> str:
        """Enhanced parameter reading with detailed information."""
        if not self.mav_handler:
            return "Not connected to drone."
        
        # Get current value
        result = read_parameter(self.mav_handler, param_name)
        
        # Add detailed information
        param_info = self.llm_handler.get_parameter_info(param_name)
        if param_info:
            result += f"\n\n{self._format_parameter_explanation(param_name, param_info)}"
            
            # Add related parameters
            related = self.llm_handler.find_related_parameters(param_name)
            if related:
                result += f"\n\n📎 **Related parameters**: {', '.join(related[:5])}"
        
        return result
    
    def _enhanced_change_parameter(self, param_name: str, new_value_str: str) -> str:
        """Enhanced parameter changing with detailed validation and feedback."""
        param_info = self.llm_handler.get_parameter_info(param_name)
        
        if not param_info:
            similar = self._find_similar_parameters(param_name)
            return f"❌ Parameter '{param_name}' not found.\n{similar}"
        
        try:
            new_value = float(new_value_str)
            min_val = param_info.get("min")
            max_val = param_info.get("max")
            units = param_info.get("units", "")
            
            # Detailed validation
            if (min_val is not None and new_value < min_val) or \
               (max_val is not None and new_value > max_val):
                
                desc = param_info.get('longDesc') or param_info.get('shortDesc', 'No description')
                
                response = f"""🛑 **PARAMETER CHANGE REJECTED**

**Parameter**: {param_name}
**Requested Value**: {new_value} {units}
**Valid Range**: [{min_val}, {max_val}] {units}

**Why this was blocked**:
The requested value is outside the safe operating range. {desc}

**What would happen if this value was set**:
"""
                
                if new_value < min_val:
                    response += f"Setting below {min_val} could cause: system instability, sensor errors, or complete failure of this subsystem."
                else:
                    response += f"Setting above {max_val} could cause: hardware damage, excessive stress, or dangerous flight behavior."
                
                # Suggest safe values
                safe_min = min_val if min_val is not None else 0
                safe_max = max_val if max_val is not None else 100
                safe_default = param_info.get('default', (safe_min + safe_max) / 2)
                
                response += f"""

**Recommended safe values**:
• Conservative: {safe_default} {units} (default)
• Minimum safe: {safe_min * 1.1 if safe_min > 0 else safe_min} {units}
• Maximum safe: {safe_max * 0.9} {units}
"""
                return response
            
            # Execute the change
            result = change_parameter(self.mav_handler, param_name, new_value_str, force=True)
            
            # Add context about the change
            result += f"""

✅ **Change Summary**:
• Parameter: {param_name}
• New Value: {new_value} {units}
• Description: {param_info.get('shortDesc', 'No description')}

This change will take effect immediately. Monitor drone behavior carefully."""
            
            return result
            
        except (ValueError, TypeError):
            return f"❌ Invalid value format '{new_value_str}'. Please provide a valid number."
    
    def _format_parameter_explanation(self, param_name: str, param_info: Dict[str, Any]) -> str:
        """Formats detailed parameter explanation."""
        explanation = [f"📖 **Parameter: {param_name}**"]
        
        if param_info.get('shortDesc'):
            explanation.append(f"**Purpose**: {param_info['shortDesc']}")
        
        if param_info.get('longDesc'):
            explanation.append(f"**Details**: {param_info['longDesc']}")
        
        units = param_info.get('units', 'no units')
        min_val = param_info.get('min', 'no minimum')
        max_val = param_info.get('max', 'no maximum')
        default = param_info.get('default', 'not specified')
        
        explanation.append(f"""
**Technical Specifications**:
• Units: {units}
• Range: [{min_val}, {max_val}]
• Default: {default}
• Type: {param_info.get('type', 'unknown')}""")
        
        if param_info.get('values'):
            explanation.append("\n**Possible Values**:")
            for value, desc in param_info['values'].items():
                explanation.append(f"  • {value}: {desc}")
        
        return "\n".join(explanation)
    
    def _find_similar_parameters(self, search_term: str, limit: int = 5) -> str:
        """Finds parameters similar to the search term."""
        search_upper = search_term.upper()
        similar = []
        
        for param in self.llm_handler._param_names:
            if search_upper in param or param in search_upper:
                similar.append(param)
                if len(similar) >= limit:
                    break
        
        if similar:
            return "Similar parameters: " + ", ".join(similar)
        return "No similar parameters found."
    
    def shutdown(self):
        """Gracefully disconnects from the drone."""
        if self.mav_handler:
            self.mav_handler.disconnect()
            logger.info("MAVLink handler disconnected.")
            print("👋 Drone disconnected. Goodbye!")


# --- Main Execution ---

if __name__ == '__main__':
    # Requires OPENAI_API_KEY environment variable
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ Error: OPENAI_API_KEY environment variable not set.")
        print("Please set it with: export OPENAI_API_KEY='your-key-here'")
    else:
        print("🚁 PX4 Drone Parameter Assistant")
        print("=" * 50)
        
        agent = AgentExecutor(api_key=api_key)
        
        print("\n📝 **Available Commands**:")
        print("• Ask about any parameter (e.g., 'What is MPC_ACC_HOR?')")
        print("• Change parameters safely (e.g., 'Set horizontal acceleration to 5')")
        print("• Search for parameters (e.g., 'Show me battery parameters')")
        print("• Get safety analysis (e.g., 'Is it safe to set pitch rate to 500?')")
        print("• Type 'exit' to quit\n")
        
        try:
            while True:
                prompt = input("🎯 You: ").strip()
                if prompt.lower() in ['exit', 'quit', 'bye']:
                    break
                if not prompt:
                    print("💭 Please enter a command or question.")
                    continue
                
                print("\n🤖 Assistant:")
                response = agent.execute_task(prompt)
                print(response)
                print("\n" + "─" * 50 + "\n")
                
        except KeyboardInterrupt:
            print("\n\n⚡ Interrupted by user")
        except Exception as e:
            print(f"\n❌ Unexpected error: {e}")
        finally:
            agent.shutdown()
            print("\n✨ Thank you for using PX4 Drone Parameter Assistant!")