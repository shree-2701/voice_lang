"""
Core Agent Framework
Implements Planner-Executor-Evaluator agentic loop with explicit state machine
"""
from enum import Enum
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime
import json
import asyncio
from abc import ABC, abstractmethod

from pydantic import BaseModel


class AgentState(str, Enum):
    """Agent lifecycle states"""
    IDLE = "idle"
    LISTENING = "listening"
    UNDERSTANDING = "understanding"
    PLANNING = "planning"
    EXECUTING = "executing"
    EVALUATING = "evaluating"
    RESPONDING = "responding"
    WAITING_FOR_INPUT = "waiting_for_input"
    ERROR_RECOVERY = "error_recovery"
    TERMINATED = "terminated"


class TaskStatus(str, Enum):
    """Status of individual tasks"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


@dataclass
class Task:
    """Represents a single task in the execution plan"""
    id: str
    description: str
    tool_name: Optional[str] = None
    tool_params: Dict[str, Any] = field(default_factory=dict)
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[Any] = None
    error: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    dependencies: List[str] = field(default_factory=list)


@dataclass
class Plan:
    """Execution plan containing multiple tasks"""
    id: str
    goal: str
    tasks: List[Task] = field(default_factory=list)
    current_task_index: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    is_complete: bool = False
    revision_count: int = 0
    
    def get_current_task(self) -> Optional[Task]:
        if self.current_task_index < len(self.tasks):
            return self.tasks[self.current_task_index]
        return None
    
    def advance(self) -> bool:
        """Move to next task, return True if there are more tasks"""
        self.current_task_index += 1
        if self.current_task_index >= len(self.tasks):
            self.is_complete = True
            self.completed_at = datetime.now()
            return False
        return True


class StateTransition(BaseModel):
    """Represents a state transition"""
    from_state: AgentState
    to_state: AgentState
    trigger: str
    timestamp: datetime = datetime.now()
    metadata: Dict[str, Any] = {}


class StateMachine:
    """
    Explicit state machine for agent lifecycle management
    Ensures valid state transitions and provides transition hooks
    """
    
    # Define valid state transitions
    VALID_TRANSITIONS = {
        AgentState.IDLE: [AgentState.LISTENING, AgentState.TERMINATED],
        AgentState.LISTENING: [AgentState.UNDERSTANDING, AgentState.ERROR_RECOVERY, AgentState.IDLE],
        AgentState.UNDERSTANDING: [AgentState.PLANNING, AgentState.WAITING_FOR_INPUT, AgentState.ERROR_RECOVERY],
        AgentState.PLANNING: [AgentState.EXECUTING, AgentState.ERROR_RECOVERY, AgentState.WAITING_FOR_INPUT],
        AgentState.EXECUTING: [AgentState.EVALUATING, AgentState.ERROR_RECOVERY, AgentState.WAITING_FOR_INPUT],
        AgentState.EVALUATING: [AgentState.RESPONDING, AgentState.PLANNING, AgentState.ERROR_RECOVERY],
        AgentState.RESPONDING: [AgentState.IDLE, AgentState.LISTENING, AgentState.WAITING_FOR_INPUT],
        AgentState.WAITING_FOR_INPUT: [AgentState.LISTENING, AgentState.IDLE, AgentState.TERMINATED],
        AgentState.ERROR_RECOVERY: [AgentState.ERROR_RECOVERY, AgentState.WAITING_FOR_INPUT, AgentState.IDLE, AgentState.RESPONDING, AgentState.TERMINATED],
        AgentState.TERMINATED: []
    }
    
    def __init__(self, initial_state: AgentState = AgentState.IDLE):
        self.current_state = initial_state
        self.transition_history: List[StateTransition] = []
        self.transition_hooks: Dict[str, List[Callable]] = {}
    
    def can_transition(self, to_state: AgentState) -> bool:
        """Check if transition to target state is valid"""
        if to_state == self.current_state:
            return True
        valid_targets = self.VALID_TRANSITIONS.get(self.current_state, [])
        return to_state in valid_targets
    
    def transition(self, to_state: AgentState, trigger: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        Execute state transition if valid
        Returns True if transition succeeded
        """
        if to_state == self.current_state:
            # Idempotent transition: treat same-state transitions as a no-op.
            # This prevents failures when recovery logic re-enters the same state.
            return True
        if not self.can_transition(to_state):
            raise InvalidStateTransitionError(
                f"Invalid transition from {self.current_state} to {to_state}"
            )
        
        transition = StateTransition(
            from_state=self.current_state,
            to_state=to_state,
            trigger=trigger,
            timestamp=datetime.now(),
            metadata=metadata or {}
        )
        
        # Execute pre-transition hooks
        self._execute_hooks(f"pre_{to_state.value}", transition)
        
        # Perform transition
        old_state = self.current_state
        self.current_state = to_state
        self.transition_history.append(transition)
        
        # Execute post-transition hooks
        self._execute_hooks(f"post_{old_state.value}", transition)
        
        return True
    
    def register_hook(self, event: str, callback: Callable):
        """Register a callback for state transition events"""
        if event not in self.transition_hooks:
            self.transition_hooks[event] = []
        self.transition_hooks[event].append(callback)
    
    def _execute_hooks(self, event: str, transition: StateTransition):
        """Execute registered hooks for an event"""
        hooks = self.transition_hooks.get(event, [])
        for hook in hooks:
            try:
                hook(transition)
            except Exception as e:
                print(f"Hook execution error: {e}")
    
    def get_history(self) -> List[Dict[str, Any]]:
        """Get transition history as serializable dict"""
        return [
            {
                "from": t.from_state.value,
                "to": t.to_state.value,
                "trigger": t.trigger,
                "timestamp": t.timestamp.isoformat(),
                "metadata": t.metadata
            }
            for t in self.transition_history
        ]


class InvalidStateTransitionError(Exception):
    """Raised when an invalid state transition is attempted"""
    pass


class BaseTool(ABC):
    """Base class for agent tools"""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Tool name"""
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """Tool description in native language"""
        pass
    
    @property
    @abstractmethod
    def parameters(self) -> Dict[str, Any]:
        """Tool parameters schema"""
        pass
    
    @abstractmethod
    async def execute(self, **kwargs) -> Dict[str, Any]:
        """Execute the tool with given parameters"""
        pass
    
    def to_schema(self) -> Dict[str, Any]:
        """Convert to OpenAI function schema format"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": self.parameters,
                    "required": [k for k, v in self.parameters.items() if v.get("required", False)]
                }
            }
        }


class ToolRegistry:
    """Registry for managing agent tools"""
    
    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}
    
    def register(self, tool: BaseTool):
        """Register a tool"""
        self._tools[tool.name] = tool
    
    def get(self, name: str) -> Optional[BaseTool]:
        """Get a tool by name"""
        return self._tools.get(name)
    
    def list_tools(self) -> List[str]:
        """List all registered tool names"""
        return list(self._tools.keys())
    
    def get_all_schemas(self) -> List[Dict[str, Any]]:
        """Get schemas for all tools"""
        return [tool.to_schema() for tool in self._tools.values()]
    
    async def execute(self, tool_name: str, **kwargs) -> Dict[str, Any]:
        """Execute a tool by name"""
        tool = self.get(tool_name)
        if not tool:
            raise ValueError(f"Tool not found: {tool_name}")
        return await tool.execute(**kwargs)


@dataclass
class EvaluationResult:
    """Result of plan/task evaluation"""
    success: bool
    confidence: float
    needs_replanning: bool
    missing_information: List[str] = field(default_factory=list)
    contradictions: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    next_action: Optional[str] = None


class AgentContext:
    """
    Shared context for the agent containing current state,
    user profile, conversation history, and active plan
    """
    
    def __init__(self):
        self.user_profile: Dict[str, Any] = {}
        self.current_plan: Optional[Plan] = None
        self.conversation_turns: List[Dict[str, Any]] = []
        self.extracted_entities: Dict[str, Any] = {}
        self.session_id: str = ""
        self.language: str = "marathi"
        self.created_at: datetime = datetime.now()
        self.last_activity: datetime = datetime.now()
    
    def update_profile(self, key: str, value: Any, source: str = "user"):
        """
        Update user profile with new information
        Tracks source and timestamp for contradiction detection
        """
        if key in self.user_profile:
            # Check for contradiction
            existing = self.user_profile[key]
            if existing.get("value") != value:
                self.user_profile[key] = {
                    "value": value,
                    "source": source,
                    "updated_at": datetime.now().isoformat(),
                    "previous_value": existing.get("value"),
                    "contradiction_detected": True
                }
                return True  # Contradiction detected
        
        self.user_profile[key] = {
            "value": value,
            "source": source,
            "updated_at": datetime.now().isoformat()
        }
        self.last_activity = datetime.now()
        return False
    
    def get_profile_value(self, key: str) -> Optional[Any]:
        """Get a value from user profile"""
        entry = self.user_profile.get(key)
        return entry.get("value") if entry else None
    
    def add_turn(self, role: str, content: str, metadata: Optional[Dict[str, Any]] = None):
        """Add a conversation turn"""
        self.conversation_turns.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {}
        })
        self.last_activity = datetime.now()
    
    def get_recent_turns(self, n: int = 10) -> List[Dict[str, Any]]:
        """Get last n conversation turns"""
        return self.conversation_turns[-n:]
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize context to dictionary"""
        return {
            "user_profile": self.user_profile,
            "extracted_entities": self.extracted_entities,
            "session_id": self.session_id,
            "language": self.language,
            "conversation_turns": self.conversation_turns,
            "created_at": self.created_at.isoformat(),
            "last_activity": self.last_activity.isoformat()
        }
