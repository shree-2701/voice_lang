"""
Planner Module
Responsible for creating execution plans based on user goals and context
"""
import json
import uuid
from typing import Dict, List, Any, Optional
from datetime import datetime

from ..config import settings
from .core import Plan, Task, TaskStatus, AgentContext, ToolRegistry


# Planning prompts in different Indian languages
PLANNER_SYSTEM_PROMPTS = {
    "marathi": """तुम्ही एक बुद्धिमान नियोजक आहात जो वापरकर्त्यांना सरकारी योजनांसाठी अर्ज करण्यात मदत करतो.

तुमचे काम:
1. वापरकर्त्याचे उद्दिष्ट समजून घ्या
2. आवश्यक माहिती ओळखा
3. कार्ये तयार करा आणि क्रमाने लावा

उपलब्ध साधने:
{tools}

वापरकर्ता प्रोफाइल:
{user_profile}

संभाषण इतिहास:
{conversation_history}

JSON स्वरूपात योजना तयार करा:
{{
    "goal": "मुख्य उद्दिष्ट",
    "reasoning": "तुमचा विचार प्रक्रिया",
    "tasks": [
        {{
            "id": "task_1",
            "description": "कार्य वर्णन",
            "tool_name": "साधन नाव",
            "tool_params": {{}},
            "dependencies": []
        }}
    ],
    "missing_info": ["आवश्यक माहिती जी गहाळ आहे"],
    "clarifying_questions": ["स्पष्टीकरणासाठी प्रश्न"]
}}""",

    "telugu": """మీరు ప్రభుత్వ పథకాల కోసం దరఖాస్తు చేయడంలో వినియోగదారులకు సహాయపడే తెలివైన ప్లానర్.

మీ పని:
1. వినియోగదారు లక్ష్యాన్ని అర్థం చేసుకోండి
2. అవసరమైన సమాచారాన్ని గుర్తించండి
3. టాస్క్‌లను సృష్టించి క్రమంలో అమర్చండి

అందుబాటులో ఉన్న సాధనాలు:
{tools}

వినియోగదారు ప్రొఫైల్:
{user_profile}

సంభాషణ చరిత్ర:
{conversation_history}

JSON ఆకృతిలో ప్రణాళికను తయారు చేయండి.""",

    "tamil": """நீங்கள் அரசு திட்டங்களுக்கு விண்ணப்பிக்க பயனர்களுக்கு உதவும் புத்திசாலி திட்டமிடுபவர்.

உங்கள் வேலை:
1. பயனரின் இலக்கைப் புரிந்துகொள்ளுங்கள்
2. தேவையான தகவல்களைக் கண்டறியுங்கள்
3. பணிகளை உருவாக்கி வரிசைப்படுத்துங்கள்

கிடைக்கும் கருவிகள்:
{tools}

பயனர் சுயவிவரம்:
{user_profile}

உரையாடல் வரலாறு:
{conversation_history}

JSON வடிவத்தில் திட்டத்தை உருவாக்குங்கள்.""",

    "hindi": """आप एक बुद्धिमान योजनाकार हैं जो उपयोगकर्ताओं को सरकारी योजनाओं के लिए आवेदन करने में मदद करते हैं।

आपका काम:
1. उपयोगकर्ता का लक्ष्य समझें
2. आवश्यक जानकारी पहचानें  
3. कार्य बनाएं और क्रम में लगाएं

उपलब्ध उपकरण:
{tools}

उपयोगकर्ता प्रोफ़ाइल:
{user_profile}

बातचीत इतिहास:
{conversation_history}

JSON प्रारूप में योजना बनाएं।""",

    "bengali": """আপনি একজন বুদ্ধিমান পরিকল্পনাকারী যিনি ব্যবহারকারীদের সরকারি প্রকল্পে আবেদন করতে সাহায্য করেন।

আপনার কাজ:
1. ব্যবহারকারীর লক্ষ্য বুঝুন
2. প্রয়োজনীয় তথ্য চিহ্নিত করুন
3. কাজ তৈরি করুন এবং সাজান

উপলব্ধ সরঞ্জাম:
{tools}

ব্যবহারকারী প্রোফাইল:
{user_profile}

কথোপকথনের ইতিহাস:
{conversation_history}

JSON ফর্ম্যাটে পরিকল্পনা তৈরি করুন।""",

    "odia": """ଆପଣ ଜଣେ ବୁଦ୍ଧିମାନ ଯୋଜନାକାରୀ ଯିଏ ସରକାରୀ ଯୋଜନା ପାଇଁ ଆବେଦନ କରିବାରେ ଉପଭୋକ୍ତାମାନଙ୍କୁ ସାହାଯ୍ୟ କରନ୍ତି।

ଆପଣଙ୍କ କାର୍ଯ୍ୟ:
1. ଉପଭୋକ୍ତାଙ୍କ ଲକ୍ଷ୍ୟ ବୁଝନ୍ତୁ
2. ଆବଶ୍ୟକ ସୂଚନା ଚିହ୍ନଟ କରନ୍ତୁ
3. କାର୍ଯ୍ୟ ତିଆରି କରନ୍ତୁ ଏବଂ କ୍ରମରେ ଲଗାନ୍ତୁ

ଉପಲବ୍ଧ ଉପକରଣ:
{tools}

ଉପଭୋକ୍ତା ପ୍ରୋଫାଇଲ୍:
{user_profile}

ବାର୍ତ୍ତାଳାପ ଇତିହାସ:
{conversation_history}

JSON ଫର୍ମାଟରେ ଯୋଜନା ପ୍ରସ୍ତୁତ କରନ୍ତୁ।"""
}


class Planner:
    """
    Planner component of the agent
    Creates execution plans based on user goals and available tools
    """
    
    def __init__(self, llm_client, tool_registry: ToolRegistry, language: str = "marathi"):
        self.llm_client = llm_client
        self.tool_registry = tool_registry
        self.language = language
    
    async def create_plan(self, goal: str, context: AgentContext) -> Plan:
        """
        Create an execution plan for the given goal
        """
        # Get system prompt in appropriate language
        system_prompt = PLANNER_SYSTEM_PROMPTS.get(
            self.language, 
            PLANNER_SYSTEM_PROMPTS["hindi"]
        )
        
        # Format tool descriptions
        tools_desc = self._format_tools_description()
        
        # Format user profile
        profile_desc = self._format_user_profile(context)
        
        # Format conversation history
        history_desc = self._format_conversation_history(context)
        
        # Build the prompt
        formatted_prompt = system_prompt.format(
            tools=tools_desc,
            user_profile=profile_desc,
            conversation_history=history_desc
        )
        
        # Call LLM to generate plan
        response = await self.llm_client.generate(
            system_prompt=formatted_prompt,
            user_message=f"वापरकर्त्याचे उद्दिष्ट: {goal}" if self.language == "marathi" else f"Goal: {goal}",
            response_format={"type": "json_object"}
        )
        
        # Parse the response
        plan_data = self._parse_plan_response(response)

        # Heuristic fallback: some local LLMs return empty/invalid plans.
        tasks_raw = plan_data.get("tasks")
        tasks_are_valid = (
            isinstance(tasks_raw, list)
            and len(tasks_raw) > 0
            and all(isinstance(t, dict) for t in tasks_raw)
        )
        if not tasks_are_valid:
            plan_data["tasks"] = self._heuristic_tasks(goal)
        
        # Create Plan object
        plan = Plan(
            id=f"plan_{uuid.uuid4().hex[:8]}",
            goal=goal,
            tasks=self._create_tasks(plan_data.get("tasks", []))
        )
        
        # Store missing info and questions in context
        if plan_data.get("missing_info"):
            context.extracted_entities["missing_info"] = plan_data["missing_info"]
        if plan_data.get("clarifying_questions"):
            context.extracted_entities["clarifying_questions"] = plan_data["clarifying_questions"]
        
        return plan

    def _heuristic_tasks(self, goal: str) -> List[Dict[str, Any]]:
        """Create a basic tool plan when the LLM planner output is unusable."""
        goal_lower = (goal or "").strip().lower()

        eligibility_cues = [
            "eligible",
            "eligibility",
            "qualify",
            "qualification",
            "apply",
            "application",
            # Tamil cues
            "தகுதி",
            "விண்ணப்ப",
            "திட்ட",
            # Hindi/Marathi cues (helps mixed speech)
            "पात्र",
            "योजना",
        ]

        wants_eligibility = any(cue in goal_lower for cue in eligibility_cues)

        tasks: List[Dict[str, Any]] = []

        if wants_eligibility:
            tasks.append({
                "id": "task_1",
                "description": "Check eligibility based on available profile information",
                "tool_name": "eligibility_checker",
                "tool_params": {
                    "age": "$context.profile.age",
                    "income": "$context.profile.income",
                    "gender": "$context.profile.gender",
                    "caste_category": "$context.profile.caste_category",
                    "state": "$context.profile.state",
                    "is_farmer": "$context.profile.is_farmer",
                    "is_bpl": "$context.profile.is_bpl",
                    "education": "$context.profile.education",
                    "occupation": "$context.profile.occupation",
                    "family_size": "$context.profile.family_size",
                    "has_land": "$context.profile.has_land",
                    "land_size": "$context.profile.land_size",
                    "is_widow": "$context.profile.is_widow",
                    "is_disabled": "$context.profile.is_disabled",
                },
                "dependencies": []
            })

            tasks.append({
                "id": "task_2",
                "description": "Retrieve relevant schemes for the user query",
                "tool_name": "scheme_retriever",
                "tool_params": {
                    "query": goal,
                    "state": "$context.profile.state",
                    "limit": 5
                },
                "dependencies": ["task_1"]
            })
        else:
            tasks.append({
                "id": "task_1",
                "description": "Retrieve relevant schemes for the user query",
                "tool_name": "scheme_retriever",
                "tool_params": {
                    "query": goal,
                    "state": "$context.profile.state",
                    "limit": 5
                },
                "dependencies": []
            })

        return tasks
    
    async def replan(self, 
                     original_plan: Plan, 
                     context: AgentContext, 
                     failure_reason: str) -> Plan:
        """
        Create a revised plan after task failure or new information
        """
        # Increment revision count
        original_plan.revision_count += 1
        
        if original_plan.revision_count > settings.max_planning_iterations:
            raise PlanningLimitExceeded(
                "Maximum replanning iterations exceeded"
            )
        
        # Get feedback from previous execution
        execution_summary = self._summarize_execution(original_plan)
        
        replan_prompt = self._get_replan_prompt(
            original_plan.goal,
            execution_summary,
            failure_reason,
            context
        )
        
        response = await self.llm_client.generate(
            system_prompt=replan_prompt,
            user_message=f"Failure reason: {failure_reason}",
            response_format={"type": "json_object"}
        )
        
        plan_data = self._parse_plan_response(response)

        tasks_raw = plan_data.get("tasks")
        tasks_are_valid = (
            isinstance(tasks_raw, list)
            and len(tasks_raw) > 0
            and all(isinstance(t, dict) for t in tasks_raw)
        )
        if not tasks_are_valid:
            plan_data["tasks"] = self._heuristic_tasks(original_plan.goal)
        
        # Create new plan with remaining tasks
        new_plan = Plan(
            id=f"plan_{uuid.uuid4().hex[:8]}",
            goal=original_plan.goal,
            tasks=self._create_tasks(plan_data.get("tasks", [])),
            revision_count=original_plan.revision_count
        )
        
        return new_plan
    
    def _format_tools_description(self) -> str:
        """Format tool descriptions for the prompt"""
        descriptions = []
        for tool_name in self.tool_registry.list_tools():
            tool = self.tool_registry.get(tool_name)
            if tool:
                descriptions.append(f"- {tool.name}: {tool.description}")
        return "\n".join(descriptions)
    
    def _format_user_profile(self, context: AgentContext) -> str:
        """Format user profile for the prompt"""
        if not context.user_profile:
            return "कोणतीही माहिती उपलब्ध नाही" if self.language == "marathi" else "No information available"
        
        profile_items = []
        for key, entry in context.user_profile.items():
            value = entry.get("value", "N/A")
            profile_items.append(f"- {key}: {value}")
        return "\n".join(profile_items)
    
    def _format_conversation_history(self, context: AgentContext) -> str:
        """Format recent conversation history"""
        recent_turns = context.get_recent_turns(5)
        if not recent_turns:
            return "कोणताही इतिहास नाही" if self.language == "marathi" else "No history"
        
        formatted = []
        for turn in recent_turns:
            role = "वापरकर्ता" if turn["role"] == "user" else "सहाय्यक"
            formatted.append(f"{role}: {turn['content']}")
        return "\n".join(formatted)
    
    def _parse_plan_response(self, response: str) -> Dict[str, Any]:
        """Parse LLM response into plan data"""
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            # Try to extract JSON from response
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            return {"tasks": [], "missing_info": [], "clarifying_questions": []}
    
    def _create_tasks(self, tasks_data: List[Dict[str, Any]]) -> List[Task]:
        """Create Task objects from plan data"""
        tasks = []
        for i, task_data in enumerate(tasks_data):
            task = Task(
                id=task_data.get("id", f"task_{i+1}"),
                description=task_data.get("description", ""),
                tool_name=task_data.get("tool_name"),
                tool_params=task_data.get("tool_params", {}),
                dependencies=task_data.get("dependencies", [])
            )
            tasks.append(task)
        return tasks
    
    def _summarize_execution(self, plan: Plan) -> str:
        """Summarize what has been executed so far"""
        summary_parts = []
        for task in plan.tasks:
            status_text = {
                TaskStatus.COMPLETED: "पूर्ण",
                TaskStatus.FAILED: "अयशस्वी",
                TaskStatus.PENDING: "बाकी",
                TaskStatus.IN_PROGRESS: "चालू"
            }.get(task.status, task.status.value)
            
            summary_parts.append(f"- {task.description}: {status_text}")
            if task.result:
                summary_parts.append(f"  परिणाम: {task.result}")
            if task.error:
                summary_parts.append(f"  त्रुटी: {task.error}")
        
        return "\n".join(summary_parts)
    
    def _get_replan_prompt(self, 
                           goal: str, 
                           execution_summary: str, 
                           failure_reason: str,
                           context: AgentContext) -> str:
        """Get prompt for replanning after failure"""
        if self.language == "marathi":
            return f"""तुम्हाला योजनेत बदल करणे आवश्यक आहे कारण एक कार्य अयशस्वी झाले.

मूळ उद्दिष्ट: {goal}

आतापर्यंतची अंमलबजावणी:
{execution_summary}

अयशस्वी होण्याचे कारण: {failure_reason}

उपलब्ध साधने:
{self._format_tools_description()}

वापरकर्ता प्रोफाइल:
{self._format_user_profile(context)}

कृपया सुधारित योजना JSON स्वरूपात द्या."""
        else:
            return f"""You need to revise the plan because a task failed.

Original goal: {goal}

Execution so far:
{execution_summary}

Failure reason: {failure_reason}

Available tools:
{self._format_tools_description()}

Please provide revised plan in JSON format."""


class PlanningLimitExceeded(Exception):
    """Raised when maximum replanning iterations are exceeded"""
    pass
