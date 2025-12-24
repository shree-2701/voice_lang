"""
Evaluator Module
Responsible for evaluating execution results and determining next steps
"""
import json
from typing import Dict, Any, List, Optional
from datetime import datetime

from .core import (
    Plan, Task, TaskStatus, AgentContext, 
    EvaluationResult, StateMachine, AgentState
)
from ..config import settings


# Evaluation prompts in Indian languages
EVALUATOR_PROMPTS = {
    "marathi": """तुम्ही एक मूल्यांकनकर्ता आहात जो योजनेच्या अंमलबजावणीचे मूल्यांकन करतो.

अंमलबजावणी परिणाम:
{execution_results}

वापरकर्ता प्रोफाइल:
{user_profile}

मूळ उद्दिष्ट: {goal}

खालील बाबींचे मूल्यांकन करा:
1. उद्दिष्ट पूर्ण झाले का?
2. कोणती माहिती अजूनही गहाळ आहे?
3. वापरकर्त्याच्या माहितीत कोणते विरोधाभास आहेत?
4. पुढील पाऊल काय असावे?

JSON स्वरूपात उत्तर द्या:
{{
    "success": true/false,
    "confidence": 0.0-1.0,
    "needs_replanning": true/false,
    "missing_information": ["गहाळ माहिती"],
    "contradictions": ["विरोधाभास"],
    "suggestions": ["सूचना"],
    "next_action": "पुढील कृती",
    "user_response": "वापरकर्त्याला देण्यासाठी प्रतिसाद"
}}""",

    "telugu": """మీరు ప్రణాళిక అమలును మూల్యాంకనం చేసే మూల్యాంకనకర్త.

అమలు ఫలితాలు:
{execution_results}

వినియోగదారు ప్రొఫైల్:
{user_profile}

అసలు లక్ష్యం: {goal}

JSON ఆకృతిలో మూల్యాంకనం అందించండి.""",

    "tamil": """நீங்கள் திட்ட செயலாக்கத்தை மதிப்பீடு செய்யும் மதிப்பீட்டாளர்.

செயலாக்க முடிவுகள்:
{execution_results}

பயனர் சுயவிவரம்:
{user_profile}

அசல் இலக்கு: {goal}

JSON வடிவத்தில் மதிப்பீட்டை வழங்கவும்.""",

    "hindi": """आप एक मूल्यांकनकर्ता हैं जो योजना के निष्पादन का मूल्यांकन करता है।

निष्पादन परिणाम:
{execution_results}

उपयोगकर्ता प्रोफ़ाइल:
{user_profile}

मूल लक्ष्य: {goal}

JSON प्रारूप में मूल्यांकन दें।""",

    "bengali": """আপনি একজন মূল্যায়নকারী যিনি পরিকল্পনা বাস্তবায়ন মূল্যায়ন করেন।

বাস্তবায়ন ফলাফল:
{execution_results}

ব্যবহারকারী প্রোফাইল:
{user_profile}

মূল লক্ষ্য: {goal}

JSON ফর্ম্যাটে মূল্যায়ন প্রদান করুন।""",

    "odia": """ଆପଣ ଜଣେ ମୂଲ୍ୟାଙ୍କନକାରୀ ଯିଏ ଯୋଜନା କାର୍ଯ୍ୟକାରିତାକୁ ମୂଲ୍ୟାଙ୍କନ କରନ୍ତି।

କାର୍ଯ୍ୟକାରିତା ଫଳାଫଳ:
{execution_results}

ଉପଭୋକ୍ତା ପ୍ରୋଫାଇଲ୍:
{user_profile}

ମୂଳ ଲକ୍ଷ୍ୟ: {goal}

JSON ଫର୍ମାଟରେ ମୂଲ୍ୟାଙ୍କନ ପ୍ରଦାନ କରନ୍ତୁ।"""
}


class Evaluator:
    """
    Evaluator component of the agent
    Evaluates execution results and determines next steps
    """
    
    def __init__(self, llm_client, language: str = "marathi"):
        self.llm_client = llm_client
        self.language = language
        self.evaluation_history: List[Dict[str, Any]] = []
    
    async def evaluate(self,
                      plan: Plan,
                      execution_results: Dict[str, Any],
                      context: AgentContext) -> EvaluationResult:
        """
        Evaluate plan execution and determine next steps
        """
        # Get prompt template
        prompt_template = EVALUATOR_PROMPTS.get(
            self.language,
            EVALUATOR_PROMPTS["hindi"]
        )
        
        # Format the prompt
        prompt = prompt_template.format(
            execution_results=json.dumps(execution_results, indent=2, ensure_ascii=False),
            user_profile=self._format_user_profile(context),
            goal=plan.goal
        )
        
        # Call LLM for evaluation
        response = await self.llm_client.generate(
            system_prompt=prompt,
            user_message="कृपया मूल्यांकन करा" if self.language == "marathi" else "Please evaluate",
            response_format={"type": "json_object"}
        )
        
        # Parse response
        eval_data = self._parse_evaluation_response(response)
        
        # Create evaluation result
        result = EvaluationResult(
            success=eval_data.get("success", False),
            confidence=eval_data.get("confidence", 0.5),
            needs_replanning=eval_data.get("needs_replanning", False),
            missing_information=eval_data.get("missing_information", []),
            contradictions=eval_data.get("contradictions", []),
            suggestions=eval_data.get("suggestions", []),
            next_action=eval_data.get("next_action")
        )
        
        # Check for contradictions in user profile
        profile_contradictions = self._detect_contradictions(context)
        result.contradictions.extend(profile_contradictions)
        
        # Update confidence threshold check
        if result.confidence < settings.confidence_threshold:
            result.needs_replanning = True
            if self.language == "marathi":
                result.suggestions.append("अधिक माहिती आवश्यक आहे")
            else:
                result.suggestions.append("More information needed")
        
        # Store user response in context
        if eval_data.get("user_response"):
            context.extracted_entities["pending_response"] = eval_data["user_response"]
        
        # Log evaluation
        self._log_evaluation(plan.id, result)
        
        return result
    
    def evaluate_input_quality(self, 
                               transcribed_text: str,
                               confidence: float) -> Dict[str, Any]:
        """
        Evaluate the quality of speech recognition input
        Returns assessment of whether input is reliable
        """
        issues = []
        
        # Check confidence
        if confidence < 0.5:
            issues.append({
                "type": "low_confidence",
                "message": (
                    "कमी आत्मविश्वास - कृपया पुन्हा बोला" if self.language == "marathi"
                    else "குறைந்த நம்பகத்தன்மை - தயவுசெய்து மீண்டும் சொல்லுங்கள்" if self.language == "tamil"
                    else "Low confidence - please repeat"
                )
            })
        
        # Check for very short input
        normalized = (transcribed_text or "").strip().lower()
        allow_short_intents = {
            "help",
            "help me",
            "need help",
            "support",
            "assist",
            # Tamil
            "உதவி",
            "உதவி வேண்டும்",
            "உதவி செய்",
            # Hindi
            "मदद",
            "मदद चाहिए",
            # Marathi
            "मदत",
            "मदत हवी",
        }

        if len(transcribed_text.split()) < 2 and normalized not in allow_short_intents:
            issues.append({
                "type": "too_short",
                "message": (
                    "खूप कमी शब्द - कृपया अधिक माहिती द्या" if self.language == "marathi"
                    else "மிகக் குறைந்த வார்த்தைகள் - தயவுசெய்து மேலும் விவரம் கூறுங்கள்" if self.language == "tamil"
                    else "Too few words - please provide more details"
                )
            })
        
        # Check for potential recognition errors (repeated words, etc.)
        words = transcribed_text.split()
        if len(words) > 2:
            consecutive_repeats = sum(
                1 for i in range(len(words)-1) 
                if words[i] == words[i+1]
            )
            if consecutive_repeats > 2:
                issues.append({
                    "type": "potential_error",
                    "message": (
                        "संभाव्य ओळख त्रुटी आढळली" if self.language == "marathi"
                        else "ஒலி/அடையாளம் பிழை இருக்கலாம்" if self.language == "tamil"
                        else "Potential recognition error detected"
                    )
                })
        
        return {
            "is_reliable": len(issues) == 0,
            "confidence": confidence,
            "issues": issues,
            "needs_confirmation": confidence < 0.7
        }
    
    def _detect_contradictions(self, context: AgentContext) -> List[str]:
        """Detect contradictions in user profile"""
        contradictions = []
        
        for key, entry in context.user_profile.items():
            if entry.get("contradiction_detected"):
                prev_value = entry.get("previous_value")
                curr_value = entry.get("value")
                
                if self.language == "marathi":
                    contradictions.append(
                        f"{key} मध्ये विरोधाभास: आधी '{prev_value}' होते, आता '{curr_value}' आहे"
                    )
                else:
                    contradictions.append(
                        f"Contradiction in {key}: was '{prev_value}', now '{curr_value}'"
                    )
        
        return contradictions
    
    def _format_user_profile(self, context: AgentContext) -> str:
        """Format user profile for evaluation"""
        if not context.user_profile:
            return "कोणतीही माहिती नाही" if self.language == "marathi" else "No information"
        
        items = []
        for key, entry in context.user_profile.items():
            value = entry.get("value", "N/A")
            items.append(f"- {key}: {value}")
        return "\n".join(items)
    
    def _parse_evaluation_response(self, response: str) -> Dict[str, Any]:
        """Parse LLM evaluation response"""
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            return {
                "success": False,
                "confidence": 0.5,
                "needs_replanning": True,
                "missing_information": [],
                "contradictions": [],
                "suggestions": []
            }
    
    def _log_evaluation(self, plan_id: str, result: EvaluationResult):
        """Log evaluation for debugging"""
        self.evaluation_history.append({
            "timestamp": datetime.now().isoformat(),
            "plan_id": plan_id,
            "success": result.success,
            "confidence": result.confidence,
            "needs_replanning": result.needs_replanning,
            "missing_info_count": len(result.missing_information),
            "contradiction_count": len(result.contradictions)
        })
    
    def get_evaluation_history(self) -> List[Dict[str, Any]]:
        """Get evaluation history"""
        return self.evaluation_history


class ContradictionResolver:
    """
    Handles resolution of contradictions in user information
    """
    
    def __init__(self, language: str = "marathi"):
        self.language = language
    
    def generate_clarification_question(self, 
                                        key: str, 
                                        old_value: Any, 
                                        new_value: Any) -> str:
        """Generate a question to clarify contradictory information"""
        templates = {
            "marathi": {
                "age": f"तुम्ही आधी वय {old_value} सांगितले होते, पण आता {new_value} सांगत आहात. कोणते बरोबर आहे?",
                "income": f"तुमचे उत्पन्न {old_value} होते की {new_value}? कृपया स्पष्ट करा.",
                "location": f"तुमचे ठिकाण {old_value} होते की {new_value}?",
                "default": f"{key} बद्दल: {old_value} बरोबर आहे की {new_value}?"
            },
            "hindi": {
                "age": f"आपने पहले उम्र {old_value} बताई थी, लेकिन अब {new_value} बता रहे हैं। कौन सी सही है?",
                "income": f"आपकी आय {old_value} थी या {new_value}? कृपया स्पष्ट करें।",
                "default": f"{key} के बारे में: {old_value} सही है या {new_value}?"
            },
            "tamil": {
                "age": f"நீங்கள் முன்பு வயது {old_value} என்று சொன்னீர்கள், இப்போது {new_value} என்று சொல்கிறீர்கள். எது சரி?",
                "income": f"உங்கள் வருமானம் {old_value} ஆ அல்லது {new_value} ஆ? தயவுசெய்து தெளிவுபடுத்துங்கள்.",
                "location": f"உங்கள் இடம் {old_value} ஆ அல்லது {new_value} ஆ?",
                "default": f"{key} குறித்து: {old_value} சரியா அல்லது {new_value} சரியா?"
            }
        }
        
        lang_templates = templates.get(self.language, templates["hindi"])
        template = lang_templates.get(key, lang_templates["default"])
        
        return template
    
    def resolve_contradiction(self,
                             context: AgentContext,
                             key: str,
                             confirmed_value: Any) -> bool:
        """
        Resolve a contradiction by setting the confirmed value
        Returns True if resolution was successful
        """
        if key in context.user_profile:
            context.user_profile[key] = {
                "value": confirmed_value,
                "source": "user_confirmed",
                "updated_at": datetime.now().isoformat(),
                "contradiction_detected": False,
                "resolved": True
            }
            return True
        return False
