"""
Memory System
Handles conversation memory, context persistence, and contradiction detection
"""
import json
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from collections import defaultdict
import hashlib


@dataclass
class MemoryEntry:
    """Single memory entry"""
    key: str
    value: Any
    source: str  # "user", "inferred", "tool_result"
    timestamp: datetime
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "value": self.value,
            "source": self.source,
            "timestamp": self.timestamp.isoformat(),
            "confidence": self.confidence,
            "metadata": self.metadata
        }


@dataclass
class ConversationTurn:
    """Single conversation turn"""
    role: str  # "user" or "assistant"
    content: str
    timestamp: datetime
    audio_confidence: float = 1.0
    entities_extracted: Dict[str, Any] = field(default_factory=dict)
    tool_calls: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "audio_confidence": self.audio_confidence,
            "entities_extracted": self.entities_extracted,
            "tool_calls": self.tool_calls
        }


class ConversationMemory:
    """
    Manages conversation history and provides context for the agent
    Implements sliding window with summarization
    """
    
    def __init__(self, max_turns: int = 20, summarize_after: int = 10):
        self.turns: List[ConversationTurn] = []
        self.max_turns = max_turns
        self.summarize_after = summarize_after
        self.summaries: List[str] = []
    
    def add_turn(self, 
                 role: str, 
                 content: str,
                 audio_confidence: float = 1.0,
                 entities: Optional[Dict[str, Any]] = None,
                 tool_calls: Optional[List[str]] = None):
        """Add a conversation turn"""
        turn = ConversationTurn(
            role=role,
            content=content,
            timestamp=datetime.now(),
            audio_confidence=audio_confidence,
            entities_extracted=entities or {},
            tool_calls=tool_calls or []
        )
        
        self.turns.append(turn)
        
        # Summarize if needed
        if len(self.turns) > self.max_turns:
            self._summarize_old_turns()
    
    def get_recent_turns(self, n: int = 10) -> List[Dict[str, Any]]:
        """Get last n turns"""
        return [t.to_dict() for t in self.turns[-n:]]
    
    def get_context_string(self, n: int = 5) -> str:
        """Get formatted conversation context"""
        context_parts = []
        
        # Include summary if available
        if self.summaries:
            context_parts.append(f"[Previous conversation summary: {self.summaries[-1]}]")
        
        # Include recent turns
        for turn in self.turns[-n:]:
            role_label = "User" if turn.role == "user" else "Assistant"
            context_parts.append(f"{role_label}: {turn.content}")
        
        return "\n".join(context_parts)
    
    def _summarize_old_turns(self):
        """Summarize older turns to maintain context window"""
        # Keep only recent turns
        turns_to_summarize = self.turns[:-self.summarize_after]
        self.turns = self.turns[-self.summarize_after:]
        
        # Create simple summary
        summary_parts = []
        for turn in turns_to_summarize:
            if turn.role == "user":
                summary_parts.append(f"User asked about: {turn.content[:50]}...")
            if turn.entities_extracted:
                summary_parts.append(f"Extracted: {list(turn.entities_extracted.keys())}")
        
        if summary_parts:
            self.summaries.append(" | ".join(summary_parts))
    
    def get_all_entities(self) -> Dict[str, Any]:
        """Get all extracted entities from conversation"""
        all_entities = {}
        for turn in self.turns:
            all_entities.update(turn.entities_extracted)
        return all_entities
    
    def clear(self):
        """Clear conversation history"""
        self.turns = []
        self.summaries = []
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "turns": [t.to_dict() for t in self.turns],
            "summaries": self.summaries
        }


class UserProfileMemory:
    """
    Manages user profile information with version tracking
    Supports contradiction detection and resolution
    """
    
    def __init__(self):
        self.entries: Dict[str, List[MemoryEntry]] = defaultdict(list)
        self.contradictions: List[Dict[str, Any]] = []
        self.confirmed_values: Dict[str, Any] = {}
    
    def set(self, 
            key: str, 
            value: Any, 
            source: str = "user",
            confidence: float = 1.0,
            metadata: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """
        Set a profile value
        Returns contradiction info if detected
        """
        entry = MemoryEntry(
            key=key,
            value=value,
            source=source,
            timestamp=datetime.now(),
            confidence=confidence,
            metadata=metadata or {}
        )
        
        # Check for contradiction
        contradiction = None
        if key in self.entries and self.entries[key]:
            last_entry = self.entries[key][-1]
            
            # Check if value is different
            if last_entry.value != value:
                # Don't flag as contradiction if it's an update from same source
                if source != "user_confirmed":
                    contradiction = {
                        "key": key,
                        "old_value": last_entry.value,
                        "old_source": last_entry.source,
                        "old_timestamp": last_entry.timestamp.isoformat(),
                        "new_value": value,
                        "new_source": source
                    }
                    self.contradictions.append(contradiction)
        
        self.entries[key].append(entry)
        
        return contradiction
    
    def get(self, key: str) -> Optional[Any]:
        """Get current value for a key"""
        # Check confirmed values first
        if key in self.confirmed_values:
            return self.confirmed_values[key]
        
        # Get latest entry
        if key in self.entries and self.entries[key]:
            return self.entries[key][-1].value
        
        return None
    
    def get_with_history(self, key: str) -> List[MemoryEntry]:
        """Get all values for a key with history"""
        return self.entries.get(key, [])
    
    def confirm_value(self, key: str, value: Any):
        """Confirm a value after contradiction resolution"""
        self.confirmed_values[key] = value
        
        # Add as new entry with high confidence
        self.set(
            key=key,
            value=value,
            source="user_confirmed",
            confidence=1.0,
            metadata={"confirmed": True}
        )
        
        # Remove from contradictions
        self.contradictions = [
            c for c in self.contradictions 
            if c["key"] != key
        ]
    
    def get_pending_contradictions(self) -> List[Dict[str, Any]]:
        """Get unresolved contradictions"""
        return [
            c for c in self.contradictions
            if c["key"] not in self.confirmed_values
        ]
    
    def get_profile_summary(self) -> Dict[str, Any]:
        """Get current profile as dictionary"""
        profile = {}
        for key in self.entries:
            value = self.get(key)
            if value is not None:
                profile[key] = value
        return profile
    
    def get_missing_fields(self, required_fields: List[str]) -> List[str]:
        """Get list of missing required fields"""
        return [f for f in required_fields if self.get(f) is None]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "profile": self.get_profile_summary(),
            "contradictions": self.contradictions,
            "confirmed_values": self.confirmed_values
        }


class SessionMemory:
    """
    Combined memory system for a session
    Integrates conversation memory and user profile
    """
    
    def __init__(self, session_id: str, language: str = "marathi"):
        self.session_id = session_id
        self.language = language
        self.conversation = ConversationMemory()
        self.profile = UserProfileMemory()
        self.tool_results: List[Dict[str, Any]] = []
        self.created_at = datetime.now()
        self.last_activity = datetime.now()
        self.current_goal: Optional[str] = None
        self.context_stack: List[str] = []
    
    def add_user_message(self, 
                         content: str, 
                         audio_confidence: float = 1.0,
                         entities: Optional[Dict[str, Any]] = None):
        """Add user message and extract entities"""
        self.conversation.add_turn(
            role="user",
            content=content,
            audio_confidence=audio_confidence,
            entities=entities
        )
        
        # Update profile with extracted entities
        if entities:
            for key, value in entities.items():
                if value is not None:
                    self.profile.set(key, value, source="extracted")
        
        self.last_activity = datetime.now()
    
    def add_assistant_message(self, 
                              content: str,
                              tool_calls: Optional[List[str]] = None):
        """Add assistant message"""
        self.conversation.add_turn(
            role="assistant",
            content=content,
            tool_calls=tool_calls
        )
        self.last_activity = datetime.now()
    
    def add_tool_result(self, tool_name: str, result: Dict[str, Any]):
        """Add tool execution result"""
        self.tool_results.append({
            "tool": tool_name,
            "result": result,
            "timestamp": datetime.now().isoformat()
        })
        self.last_activity = datetime.now()
    
    def set_goal(self, goal: str):
        """Set current conversation goal"""
        self.current_goal = goal
        self.context_stack.append(goal)
    
    def get_full_context(self) -> Dict[str, Any]:
        """Get complete context for agent"""
        return {
            "session_id": self.session_id,
            "language": self.language,
            "current_goal": self.current_goal,
            "user_profile": self.profile.get_profile_summary(),
            "conversation_context": self.conversation.get_context_string(),
            "recent_turns": self.conversation.get_recent_turns(5),
            "pending_contradictions": self.profile.get_pending_contradictions(),
            "recent_tool_results": self.tool_results[-3:] if self.tool_results else [],
            "session_duration": (datetime.now() - self.created_at).total_seconds()
        }
    
    def has_pending_contradictions(self) -> bool:
        """Check if there are unresolved contradictions"""
        return len(self.profile.get_pending_contradictions()) > 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "language": self.language,
            "conversation": self.conversation.to_dict(),
            "profile": self.profile.to_dict(),
            "tool_results": self.tool_results,
            "current_goal": self.current_goal,
            "context_stack": self.context_stack,
            "created_at": self.created_at.isoformat(),
            "last_activity": self.last_activity.isoformat()
        }
    
    def save_to_file(self, filepath: str):
        """Save session to file"""
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
    
    @classmethod
    def load_from_file(cls, filepath: str) -> 'SessionMemory':
        """Load session from file"""
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        session = cls(data["session_id"], data["language"])
        
        # Restore conversation
        for turn_data in data.get("conversation", {}).get("turns", []):
            session.conversation.turns.append(ConversationTurn(
                role=turn_data["role"],
                content=turn_data["content"],
                timestamp=datetime.fromisoformat(turn_data["timestamp"]),
                audio_confidence=turn_data.get("audio_confidence", 1.0),
                entities_extracted=turn_data.get("entities_extracted", {}),
                tool_calls=turn_data.get("tool_calls", [])
            ))
        
        # Restore profile
        profile_data = data.get("profile", {}).get("profile", {})
        for key, value in profile_data.items():
            session.profile.set(key, value, source="restored")
        
        session.tool_results = data.get("tool_results", [])
        session.current_goal = data.get("current_goal")
        session.context_stack = data.get("context_stack", [])
        
        return session


class MemoryManager:
    """
    Manages multiple session memories
    Handles session creation, retrieval, and cleanup
    """
    
    def __init__(self, max_sessions: int = 100, session_timeout_hours: int = 24):
        self.sessions: Dict[str, SessionMemory] = {}
        self.max_sessions = max_sessions
        self.session_timeout = timedelta(hours=session_timeout_hours)
    
    def create_session(self, session_id: str, language: str = "marathi") -> SessionMemory:
        """Create new session"""
        # Cleanup old sessions if needed
        if len(self.sessions) >= self.max_sessions:
            self._cleanup_old_sessions()
        
        session = SessionMemory(session_id, language)
        self.sessions[session_id] = session
        return session
    
    def get_session(self, session_id: str) -> Optional[SessionMemory]:
        """Get existing session"""
        session = self.sessions.get(session_id)
        if session:
            # Check if expired
            if datetime.now() - session.last_activity > self.session_timeout:
                del self.sessions[session_id]
                return None
        return session
    
    def get_or_create_session(self, 
                              session_id: str, 
                              language: str = "marathi") -> SessionMemory:
        """Get existing or create new session"""
        session = self.get_session(session_id)
        if not session:
            session = self.create_session(session_id, language)
        return session
    
    def end_session(self, session_id: str):
        """End and remove session"""
        if session_id in self.sessions:
            del self.sessions[session_id]
    
    def _cleanup_old_sessions(self):
        """Remove expired sessions"""
        now = datetime.now()
        expired = [
            sid for sid, session in self.sessions.items()
            if now - session.last_activity > self.session_timeout
        ]
        for sid in expired:
            del self.sessions[sid]
        
        # If still too many, remove oldest
        if len(self.sessions) >= self.max_sessions:
            sorted_sessions = sorted(
                self.sessions.items(),
                key=lambda x: x[1].last_activity
            )
            for sid, _ in sorted_sessions[:len(sorted_sessions)//2]:
                del self.sessions[sid]
    
    def get_all_session_ids(self) -> List[str]:
        """Get all active session IDs"""
        return list(self.sessions.keys())
