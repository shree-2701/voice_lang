"""
Main Agent Orchestrator
Coordinates the Planner-Executor-Evaluator loop
"""
import asyncio
import uuid
from typing import Dict, Any, Optional, Callable
from datetime import datetime

from .core import (
    StateMachine, AgentState, AgentContext, 
    ToolRegistry, Plan, EvaluationResult
)
from .planner import Planner, PlanningLimitExceeded
from .executor import Executor, ExecutionError
from .evaluator import Evaluator, ContradictionResolver
from ..config import settings


class VoiceAgent:
    """
    Main agent orchestrator that manages the complete agentic workflow
    Implements Planner-Executor-Evaluator loop with state machine
    """
    
    def __init__(self, 
                 llm_client,
                 tool_registry: ToolRegistry,
                 language: str = "marathi"):
        self.llm_client = llm_client
        self.tool_registry = tool_registry
        self.language = language
        
        # Initialize state machine
        self.state_machine = StateMachine(AgentState.IDLE)
        
        # Initialize components
        self.planner = Planner(llm_client, tool_registry, language)
        self.executor = Executor(tool_registry, self.state_machine, language)
        self.evaluator = Evaluator(llm_client, language)
        self.contradiction_resolver = ContradictionResolver(language)
        
        # Session management
        self.sessions: Dict[str, AgentContext] = {}
        
        # Event callbacks
        self.on_state_change: Optional[Callable] = None
        self.on_response: Optional[Callable] = None
        
        # Register state change hook
        self.state_machine.register_hook(
            "post_idle", 
            self._on_state_change
        )
    
    def create_session(self) -> str:
        """Create a new conversation session"""
        session_id = f"session_{uuid.uuid4().hex[:8]}"
        context = AgentContext()
        context.session_id = session_id
        context.language = self.language
        self.sessions[session_id] = context
        return session_id
    
    def get_context(self, session_id: str) -> Optional[AgentContext]:
        """Get context for a session"""
        return self.sessions.get(session_id)
    
    async def process_input(self, 
                           session_id: str,
                           user_input: str,
                           input_confidence: float = 1.0) -> Dict[str, Any]:
        """
        Main entry point for processing user input
        Implements the full Planner-Executor-Evaluator loop
        """
        context = self.get_context(session_id)
        if not context:
            return {"error": "Invalid session", "response": self._get_error_message("invalid_session")}
        
        try:
            # Transition to LISTENING state
            self.state_machine.transition(
                AgentState.LISTENING,
                "user_input_received",
                {"input": user_input}
            )
            
            # Step 1: Evaluate input quality
            input_evaluation = self.evaluator.evaluate_input_quality(
                user_input, 
                input_confidence
            )
            
            if not input_evaluation["is_reliable"]:
                return await self._handle_unreliable_input(
                    context, 
                    user_input, 
                    input_evaluation
                )
            
            # Add user input to conversation history
            context.add_turn("user", user_input, {"confidence": input_confidence})
            
            # Transition to UNDERSTANDING state
            self.state_machine.transition(
                AgentState.UNDERSTANDING,
                "input_validated",
                {"confidence": input_confidence}
            )
            
            # Step 2: Extract entities and update profile
            entities = await self._extract_entities(user_input, context)
            await self._update_profile_from_entities(entities, context)
            
            # Check for contradictions
            contradictions = self._check_for_contradictions(context)
            if contradictions:
                return await self._handle_contradictions(context, contradictions)
            
            # Step 3: Create plan
            self.state_machine.transition(
                AgentState.PLANNING,
                "understanding_complete",
                {"entities": entities}
            )
            
            plan = await self.planner.create_plan(user_input, context)
            context.current_plan = plan
            
            # Check if plan requires more information
            if context.extracted_entities.get("clarifying_questions"):
                return await self._request_clarification(context)
            
            # Step 4: Execute plan
            self.state_machine.transition(
                AgentState.EXECUTING,
                "plan_created",
                {"plan_id": plan.id, "task_count": len(plan.tasks)}
            )
            
            execution_results = await self.executor.execute_plan(plan, context)
            
            # Step 5: Evaluate results
            self.state_machine.transition(
                AgentState.EVALUATING,
                "execution_complete",
                {"status": execution_results["final_status"]}
            )
            
            evaluation = await self.evaluator.evaluate(plan, execution_results, context)
            
            # Step 6: Handle evaluation result
            if evaluation.needs_replanning and plan.revision_count < settings.max_planning_iterations:
                # Replan and re-execute
                return await self._handle_replanning(context, plan, evaluation)
            
            # Step 7: Generate response
            self.state_machine.transition(
                AgentState.RESPONDING,
                "evaluation_complete",
                {"success": evaluation.success}
            )
            
            response = await self._generate_response(context, evaluation, execution_results)
            
            # Add response to conversation history
            context.add_turn("assistant", response["text"])
            
            # Transition back to IDLE or WAITING_FOR_INPUT
            if evaluation.missing_information:
                self.state_machine.transition(
                    AgentState.WAITING_FOR_INPUT,
                    "awaiting_user_response"
                )
            else:
                self.state_machine.transition(
                    AgentState.IDLE,
                    "interaction_complete"
                )
            
            return response
            
        except PlanningLimitExceeded as e:
            return await self._handle_error(context, "planning_limit", str(e))
        except ExecutionError as e:
            return await self._handle_error(context, "execution_error", str(e))
        except Exception as e:
            return await self._handle_error(context, "unexpected_error", str(e))
    
    async def _extract_entities(self, 
                               user_input: str, 
                               context: AgentContext) -> Dict[str, Any]:
        """Extract entities from user input using LLM"""
        extraction_prompt = self._get_entity_extraction_prompt()
        
        response = await self.llm_client.generate(
            system_prompt=extraction_prompt,
            user_message=user_input,
            response_format={"type": "json_object"}
        )
        
        try:
            import json
            entities = json.loads(response)
            context.extracted_entities.update(entities)
            return entities
        except:
            return {}
    
    async def _update_profile_from_entities(self,
                                           entities: Dict[str, Any],
                                           context: AgentContext):
        """Update user profile from extracted entities"""
        profile_fields = [
            "age", "income", "occupation", "location", "state",
            "district", "gender", "caste_category", "education",
            "family_size", "is_farmer", "is_bpl", "has_land",
            "land_size", "is_widow", "is_disabled", "ration_card_type"
        ]
        
        for field in profile_fields:
            if field in entities and entities[field]:
                contradiction = context.update_profile(
                    field, 
                    entities[field], 
                    source="extracted"
                )
                if contradiction:
                    context.extracted_entities.setdefault(
                        "detected_contradictions", []
                    ).append(field)
    
    def _check_for_contradictions(self, context: AgentContext) -> list:
        """Check for contradictions in user profile"""
        contradictions = []
        for key, entry in context.user_profile.items():
            if entry.get("contradiction_detected"):
                contradictions.append({
                    "field": key,
                    "old_value": entry.get("previous_value"),
                    "new_value": entry.get("value")
                })
        return contradictions
    
    async def _handle_contradictions(self,
                                    context: AgentContext,
                                    contradictions: list) -> Dict[str, Any]:
        """Handle detected contradictions by asking for clarification"""
        self.state_machine.transition(
            AgentState.WAITING_FOR_INPUT,
            "contradiction_detected"
        )
        
        # Generate clarification question for first contradiction
        contradiction = contradictions[0]
        question = self.contradiction_resolver.generate_clarification_question(
            contradiction["field"],
            contradiction["old_value"],
            contradiction["new_value"]
        )
        
        context.extracted_entities["pending_contradiction"] = contradiction
        
        return {
            "text": question,
            "type": "clarification",
            "requires_input": True,
            "contradiction": contradiction
        }
    
    async def _handle_unreliable_input(self,
                                       context: AgentContext,
                                       user_input: str,
                                       evaluation: Dict[str, Any]) -> Dict[str, Any]:
        """Handle unreliable speech recognition input"""
        self.state_machine.transition(
            AgentState.ERROR_RECOVERY,
            "unreliable_input",
            evaluation
        )
        
        issues = evaluation.get("issues", [])
        
        if self.language == "marathi":
            if any(i["type"] == "low_confidence" for i in issues):
                message = "मला नीट ऐकू आले नाही. कृपया पुन्हा स्पष्टपणे बोला."
            elif any(i["type"] == "too_short" for i in issues):
                message = "कृपया अधिक तपशील द्या. तुम्हाला काय हवे आहे ते सविस्तर सांगा."
            else:
                message = "कृपया पुन्हा प्रयत्न करा."
        elif self.language == "tamil":
            if any(i["type"] == "low_confidence" for i in issues):
                message = "எனக்கு தெளிவாக கேட்கவில்லை. தயவுசெய்து மீண்டும் தெளிவாக பேசுங்கள்."
            elif any(i["type"] == "too_short" for i in issues):
                message = "தயவுசெய்து மேலும் விவரம் கூறுங்கள். எந்த திட்ட உதவி வேண்டும்?"
            else:
                message = "தயவுசெய்து மீண்டும் முயற்சிக்கவும்."
        else:
            if any(i["type"] == "low_confidence" for i in issues):
                message = "I couldn't hear you clearly. Please speak again."
            else:
                message = "Please try again with more details."
        
        self.state_machine.transition(
            AgentState.WAITING_FOR_INPUT,
            "requesting_retry"
        )
        
        return {
            "text": message,
            "type": "retry_request",
            "requires_input": True,
            "issues": issues
        }
    
    async def _request_clarification(self, context: AgentContext) -> Dict[str, Any]:
        """Request clarification for missing information"""
        self.state_machine.transition(
            AgentState.WAITING_FOR_INPUT,
            "requesting_clarification"
        )
        
        questions = context.extracted_entities.get("clarifying_questions", [])
        question = questions[0] if questions else self._get_default_clarification()
        
        return {
            "text": question,
            "type": "clarification",
            "requires_input": True
        }
    
    async def _handle_replanning(self,
                                context: AgentContext,
                                original_plan: Plan,
                                evaluation: EvaluationResult) -> Dict[str, Any]:
        """Handle replanning after evaluation failure"""
        self.state_machine.transition(
            AgentState.PLANNING,
            "replanning",
            {"reason": "evaluation_failed"}
        )
        
        # Create failure reason from evaluation
        failure_reasons = []
        if evaluation.missing_information:
            failure_reasons.extend(evaluation.missing_information)
        if evaluation.contradictions:
            failure_reasons.extend(evaluation.contradictions)
        
        failure_reason = "; ".join(failure_reasons) or "Execution incomplete"
        
        try:
            # Create revised plan
            new_plan = await self.planner.replan(
                original_plan,
                context,
                failure_reason
            )
            context.current_plan = new_plan
            
            # Execute revised plan
            self.state_machine.transition(
                AgentState.EXECUTING,
                "executing_revised_plan"
            )
            
            execution_results = await self.executor.execute_plan(new_plan, context)
            
            # Evaluate again
            self.state_machine.transition(
                AgentState.EVALUATING,
                "evaluating_revised_execution"
            )
            
            new_evaluation = await self.evaluator.evaluate(
                new_plan, 
                execution_results, 
                context
            )
            
            # Generate response
            self.state_machine.transition(
                AgentState.RESPONDING,
                "generating_response"
            )
            
            return await self._generate_response(
                context, 
                new_evaluation, 
                execution_results
            )
            
        except PlanningLimitExceeded:
            return await self._handle_error(
                context, 
                "planning_limit",
                "Maximum replanning attempts exceeded"
            )
    
    async def _generate_response(self,
                                context: AgentContext,
                                evaluation: EvaluationResult,
                                execution_results: Dict[str, Any]) -> Dict[str, Any]:
        """Generate natural language response for the user"""
        response_prompt = self._get_response_generation_prompt()
        
        response = await self.llm_client.generate(
            system_prompt=response_prompt,
            user_message=f"""
Evaluation: {evaluation.__dict__}
Execution Results: {execution_results}
User Profile: {context.user_profile}
Language: {self.language}
""",
            response_format={"type": "json_object"}
        )
        
        try:
            import json
            response_data = json.loads(response)

            response_text = (response_data.get("response") or "").strip()
            # Local LLMs sometimes echo placeholders from the prompt.
            placeholder_texts = {
                "பயனருக்கான தமிழ் பதில்",
                "வापरकर्त्यासाठी मराठीत प्रतिसाद",
                "Your response to the user",
                "<your response to the user>",
            }
            normalized = response_text.strip().strip("<>").strip().lower()
            if (not response_text) or (response_text in placeholder_texts) or (normalized == "your response to the user"):
                return self._generate_fallback_response(context, evaluation, execution_results)

            if self._is_unusable_response_text(response_text):
                return self._generate_fallback_response(context, evaluation, execution_results)

            # If we have concrete tool results but the model didn't mention any scheme,
            # prefer deterministic output over a generic sentence.
            eligible = context.extracted_entities.get("eligible_schemes") or []
            retrieved = context.extracted_entities.get("retrieved_schemes") or []
            if (eligible or retrieved) and (not self._mentions_any_scheme(response_text, eligible, retrieved)):
                return self._generate_fallback_response(context, evaluation, execution_results)

            return {
                "text": response_text,
                "type": "response",
                "eligible_schemes": response_data.get("eligible_schemes", []),
                "next_steps": response_data.get("next_steps", []),
                "requires_input": bool(evaluation.missing_information)
            }
        except:
            pending = (context.extracted_entities.get("pending_response") or "").strip()
            if pending:
                return {
                    "text": pending,
                    "type": "response",
                    "requires_input": False
                }
            return self._generate_fallback_response(context, evaluation, execution_results)

    def _is_unusable_response_text(self, text: str) -> bool:
        """Heuristic filter for bad LLM outputs (e.g., gibberish or wrong-script placeholders)."""
        t = (text or "").strip()
        if not t:
            return True

        lower = t.lower()
        obvious_bad = [
            "what even is that",
            "as an ai",
            "i can't",
            "i cannot",
            "i don't know",
        ]
        if any(p in lower for p in obvious_bad):
            return True

        # In Tamil mode, reject very short/noisy strings and non-Tamil script answers.
        if self.language == "tamil":
            nonspace = [ch for ch in t if not ch.isspace()]
            if len(nonspace) < 12:
                return True

            tamil_letters = sum(1 for ch in nonspace if "\u0B80" <= ch <= "\u0BFF")
            latin_letters = sum(1 for ch in nonspace if ("a" <= ch.lower() <= "z"))
            digits = sum(1 for ch in nonspace if ch.isdigit())

            # If it contains digits and is short, it's likely garbled.
            if digits > 0 and len(nonspace) < 40:
                return True

            # If it's mostly not Tamil and also not a substantial English response, treat as unusable.
            tamil_ratio = tamil_letters / max(1, len(nonspace))
            if tamil_ratio < 0.25 and latin_letters < 20:
                return True

        return False

    def _mentions_any_scheme(self, response_text: str, eligible: list, retrieved: list) -> bool:
        """Return True if response_text appears to mention at least one known scheme name."""
        text = (response_text or "").lower()
        if not text:
            return False

        def _candidate_names_from_eligible(items: list) -> list[str]:
            names: list[str] = []
            for item in items:
                if isinstance(item, str):
                    if item.strip():
                        names.append(item.strip())
                    continue
                if isinstance(item, dict):
                    scheme = item.get("scheme") if isinstance(item.get("scheme"), dict) else None
                    if scheme:
                        for k in ("name", "name_en", "id"):
                            v = scheme.get(k)
                            if isinstance(v, str) and v.strip():
                                names.append(v.strip())
                    else:
                        for k in ("scheme_name", "name", "name_en", "id"):
                            v = item.get(k)
                            if isinstance(v, str) and v.strip():
                                names.append(v.strip())
            return names

        def _candidate_names_from_retrieved(items: list) -> list[str]:
            names: list[str] = []
            for item in items:
                if isinstance(item, str):
                    if item.strip():
                        names.append(item.strip())
                    continue
                if isinstance(item, dict):
                    for k in ("name", "name_en", "id"):
                        v = item.get(k)
                        if isinstance(v, str) and v.strip():
                            names.append(v.strip())
            return names

        candidates = _candidate_names_from_eligible(eligible) + _candidate_names_from_retrieved(retrieved)
        # Check only a few candidates to keep it cheap.
        for name in candidates[:8]:
            n = name.lower()
            if len(n) < 4:
                continue
            if n in text:
                return True
        return False

    def _generate_fallback_response(self,
                                    context: AgentContext,
                                    evaluation: EvaluationResult,
                                    execution_results: Dict[str, Any]) -> Dict[str, Any]:
        """Generate a deterministic response from tool outputs when LLM output is unusable."""
        eligible = context.extracted_entities.get("eligible_schemes") or []
        retrieved = context.extracted_entities.get("retrieved_schemes") or []

        def _scheme_name(value: Any, *, prefer_lang: str) -> str:
            """Extract a display name from either a scheme dict or a string."""
            if isinstance(value, str):
                return value.strip() or ("திட்டம்" if prefer_lang == "tamil" else "scheme")
            if isinstance(value, dict):
                if prefer_lang == "tamil":
                    return (
                        value.get("name")
                        or value.get("name_ta")
                        or value.get("name_en")
                        or "திட்டம்"
                    )
                return value.get("name_en") or value.get("name") or "scheme"
            return "திட்டம்" if prefer_lang == "tamil" else "scheme"

        if self.language == "tamil":
            if eligible:
                top = eligible[:3]
                names = []
                for item in top:
                    if isinstance(item, dict) and "scheme" in item and isinstance(item.get("scheme"), dict):
                        scheme = item.get("scheme") or {}
                        names.append(_scheme_name(scheme, prefer_lang="tamil"))
                    else:
                        names.append(_scheme_name(item, prefer_lang="tamil"))
                text = "உங்கள் தகவலின் அடிப்படையில் நீங்கள் தகுதியுள்ள திட்டங்கள்:\n" + "\n".join([f"- {n}" for n in names])
                text += "\n\nஅடுத்த படி: உங்கள் வயது, வருமானம், தொழில், மாநிலம் ஆகியவற்றை உறுதிப்படுத்துங்கள்."
                return {"text": text, "type": "response", "requires_input": True}

            if retrieved:
                top = retrieved[:3]
                names = [_scheme_name(s, prefer_lang="tamil") for s in top]
                text = "உங்களுக்கு தொடர்புடைய சில அரசு திட்டங்கள்:\n" + "\n".join([f"- {n}" for n in names])
                text += "\n\nநீங்கள் எந்த வகை உதவி தேடுகிறீர்கள்? (உதா: விவசாயம்/வீடு/மகளிர் நலன்/பென்ஷன்)"
                return {"text": text, "type": "response", "requires_input": True}

            text = "நீங்கள் எந்த திட்டத்திற்கு விண்ணப்பிக்க விரும்புகிறீர்கள்?\nதயவுசெய்து உங்கள் வயது, வருமானம், தொழில், மாநிலம் ஆகியவற்றை சொல்லுங்கள்."
            return {"text": text, "type": "clarification", "requires_input": True}

        # Default English fallback
        if eligible:
            names = []
            for item in eligible[:3]:
                if isinstance(item, dict) and "scheme" in item and isinstance(item.get("scheme"), dict):
                    scheme = item.get("scheme") or {}
                    names.append(_scheme_name(scheme, prefer_lang="en"))
                else:
                    names.append(_scheme_name(item, prefer_lang="en"))
            text = "Based on what you shared, these schemes may apply:\n" + "\n".join([f"- {n}" for n in names])
            text += "\n\nPlease confirm your age, income, occupation, and state."
            return {"text": text, "type": "response", "requires_input": True}

        if retrieved:
            names = [_scheme_name(s, prefer_lang="en") for s in retrieved[:3]]
            text = "Here are some relevant schemes:\n" + "\n".join([f"- {n}" for n in names])
            text += "\n\nTell me your age, income, occupation, and state to check eligibility."
            return {"text": text, "type": "response", "requires_input": True}

        return {
            "text": self._get_default_clarification(),
            "type": "clarification",
            "requires_input": True
        }
    
    async def _handle_error(self,
                           context: AgentContext,
                           error_type: str,
                           error_message: str) -> Dict[str, Any]:
        """Handle errors gracefully"""
        # Best-effort logging for diagnosis (especially useful in local, no-API setups).
        try:
            import traceback
            print(f"[VoiceAgent] Error type={error_type} message={error_message}")
            print(traceback.format_exc())
        except Exception:
            pass

        self.state_machine.transition(
            AgentState.ERROR_RECOVERY,
            f"error_{error_type}",
            {"error": error_message}
        )
        
        error_response = self._get_error_message(error_type)
        if getattr(settings, "debug", False) and error_message:
            # Surface the root cause in UI while in debug mode.
            error_response = f"{error_response} (debug: {error_message})"
        
        self.state_machine.transition(
            AgentState.IDLE,
            "error_handled"
        )
        
        return {
            "text": error_response,
            "type": "error",
            "error_type": error_type,
            "error_message": error_message,
            "requires_input": True
        }
    
    def _get_entity_extraction_prompt(self) -> str:
        """Get entity extraction prompt"""
        if self.language == "marathi":
            return """वापरकर्त्याच्या संदेशातून खालील माहिती काढा (JSON स्वरूपात):
- age (वय)
- income (वार्षिक उत्पन्न)
- occupation (व्यवसाय)
- location (स्थान/गाव)
- state (राज्य)
- district (जिल्हा)
- gender (लिंग)
- caste_category (जात वर्ग: SC/ST/OBC/General)
- education (शिक्षण)
- family_size (कुटुंबातील सदस्य संख्या)
- is_farmer (शेतकरी आहे का)
- is_bpl (दारिद्र्य रेषेखाली)
- intent (वापरकर्त्याचा उद्देश)

फक्त JSON द्या, अतिरिक्त मजकूर नाही."""
        return """Extract the following from user message (in JSON):
- age, income, occupation, location, state, district, gender, 
- caste_category, education, family_size, is_farmer, is_bpl, intent

Return only JSON, no extra text."""
    
    def _get_response_generation_prompt(self) -> str:
        """Get response generation prompt"""
        if self.language == "marathi":
            return """तुम्ही एक सरकारी योजना सहाय्यक आहात. 
वापरकर्त्याला मराठीत मदत करा.
JSON स्वरूपात उत्तर द्या:
{
    "response": "वापरकर्त्यासाठी मराठीत प्रतिसाद",
    "eligible_schemes": ["पात्र योजनांची यादी"],
    "next_steps": ["पुढील पावले"]
}"""

        if self.language == "tamil":
            return """நீங்கள் அரசு திட்ட உதவியாளர்.
பயனருக்கு தமிழில் உதவுங்கள்.
கீழ்கண்ட JSON வடிவத்தில் மட்டும் பதிலளியுங்கள் (உதாரண மதிப்புகளை நகலெடுக்க வேண்டாம்):
{
    "response": "...",
    "eligible_schemes": ["..."],
    "next_steps": ["..."]
}"""

        return """You are a government scheme assistant.
Help the user in their language.
Return JSON with: response, eligible_schemes, next_steps"""
    
    def _get_error_message(self, error_type: str) -> str:
        """Get error message in current language"""
        messages = {
            "marathi": {
                "invalid_session": "सत्र अवैध आहे. कृपया पुन्हा सुरू करा.",
                "planning_limit": "मला योजना बनवता आली नाही. कृपया पुन्हा प्रयत्न करा.",
                "execution_error": "काहीतरी चूक झाली. कृपया पुन्हा प्रयत्न करा.",
                "unexpected_error": "अनपेक्षित त्रुटी. कृपया पुन्हा प्रयत्न करा."
            },
            "hindi": {
                "invalid_session": "सत्र अमान्य है। कृपया फिर से शुरू करें।",
                "planning_limit": "योजना नहीं बन पाई। कृपया पुनः प्रयास करें।",
                "execution_error": "कुछ गलत हुआ। कृपया पुनः प्रयास करें।",
                "unexpected_error": "अप्रत्याशित त्रुटि। कृपया पुनः प्रयास करें।"
            },
            "tamil": {
                "invalid_session": "அமர்வு தவறானது. தயவுசெய்து மீண்டும் தொடங்குங்கள்.",
                "planning_limit": "திட்டமிட முடியவில்லை. தயவுசெய்து மீண்டும் முயற்சிக்கவும்.",
                "execution_error": "ஏதோ தவறு ஏற்பட்டது. தயவுசெய்து மீண்டும் முயற்சிக்கவும்.",
                "unexpected_error": "எதிர்பாராத பிழை. தயவுசெய்து மீண்டும் முயற்சிக்கவும்."
            }
        }
        
        lang_messages = messages.get(self.language, messages["hindi"])
        return lang_messages.get(error_type, lang_messages["unexpected_error"])
    
    def _get_default_clarification(self) -> str:
        """Get default clarification request"""
        if self.language == "marathi":
            return "कृपया अधिक माहिती द्या. तुमचे वय, उत्पन्न आणि व्यवसाय काय आहे?"
        if self.language == "tamil":
            return "தயவுசெய்து மேலும் தகவல் வழங்குங்கள். உங்கள் வயது, வருமானம், தொழில் என்ன?"
        return "Please provide more information. What is your age, income and occupation?"
    
    def _on_state_change(self, transition):
        """Callback for state changes"""
        if self.on_state_change:
            self.on_state_change(transition)
    
    def get_state(self) -> AgentState:
        """Get current agent state"""
        return self.state_machine.current_state
    
    def get_state_history(self) -> list:
        """Get state transition history"""
        return self.state_machine.get_history()
    
    def end_session(self, session_id: str):
        """End a session and cleanup"""
        if session_id in self.sessions:
            del self.sessions[session_id]
        
        if self.state_machine.current_state != AgentState.TERMINATED:
            self.state_machine.transition(
                AgentState.IDLE,
                "session_ended"
            )
