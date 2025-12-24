# Architecture Documentation

## System Overview

The Voice-First Agentic AI System is designed as a modular, extensible platform for government scheme assistance in Indian languages. This document provides detailed architectural decisions and component descriptions.

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            User Interface Layer                              │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────────┐  │
│  │   CLI Interface │  │  Gradio Web UI  │  │    FastAPI REST/WebSocket   │  │
│  │    (main.py)    │  │    (app.py)     │  │        (server.py)          │  │
│  └────────┬────────┘  └────────┬────────┘  └──────────────┬──────────────┘  │
└───────────┼────────────────────┼──────────────────────────┼─────────────────┘
            │                    │                          │
            └────────────────────┼──────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Voice Processing Layer                             │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────┐          ┌─────────────────────────┐           │
│  │      STT Module         │          │      TTS Module         │           │
│  │   (voice/stt.py)        │          │   (voice/tts.py)        │           │
│  │                         │          │                         │           │
│  │  ┌──────────────────┐   │          │  ┌──────────────────┐   │           │
│  │  │ WhisperSTT       │   │          │  │ AzureTTS         │   │           │
│  │  │ GoogleSTT        │   │          │  │ GoogleTTS        │   │           │
│  │  │ AzureSTT         │   │          │  │ Pyttsx3TTS       │   │           │
│  │  └──────────────────┘   │          │  └──────────────────┘   │           │
│  └─────────────────────────┘          └─────────────────────────┘           │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    Audio Processing (voice/audio.py)                 │    │
│  │                AudioRecorder | AudioPlayer | StreamingProcessor      │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            Agent Core Layer                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                     VoiceAgent Orchestrator                          │    │
│  │                     (agent/orchestrator.py)                          │    │
│  │                                                                      │    │
│  │         ┌──────────────────────────────────────────────┐            │    │
│  │         │            State Machine (core.py)            │            │    │
│  │         │  IDLE → LISTENING → UNDERSTANDING → PLANNING  │            │    │
│  │         │     → EXECUTING → EVALUATING → RESPONDING     │            │    │
│  │         └──────────────────────────────────────────────┘            │    │
│  │                                                                      │    │
│  │  ┌────────────────┐ ┌────────────────┐ ┌────────────────┐           │    │
│  │  │    Planner     │ │   Executor     │ │   Evaluator    │           │    │
│  │  │ (planner.py)   │ │ (executor.py)  │ │ (evaluator.py) │           │    │
│  │  │                │ │                │ │                │           │    │
│  │  │ - Intent       │ │ - Run Tools    │ │ - Check Output │           │    │
│  │  │ - Task List    │ │ - Get Results  │ │ - Detect Issues│           │    │
│  │  │ - Dependencies │ │ - Update Ctx   │ │ - Replan?      │           │    │
│  │  └────────────────┘ └────────────────┘ └────────────────┘           │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            Tools & Memory Layer                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                        Tool Registry (core.py)                       │    │
│  │                                                                      │    │
│  │  ┌────────────────────┐  ┌────────────────────┐                     │    │
│  │  │ EligibilityChecker │  │  SchemeRetriever   │                     │    │
│  │  │ (eligibility.py)   │  │  (retrieval.py)    │                     │    │
│  │  │                    │  │                    │                     │    │
│  │  │ - 10+ Schemes      │  │ - Keyword Search   │                     │    │
│  │  │ - Criteria Match   │  │ - Category Filter  │                     │    │
│  │  │ - Score Calculation│  │ - Semantic Search  │                     │    │
│  │  └────────────────────┘  └────────────────────┘                     │    │
│  │                                                                      │    │
│  │  ┌────────────────────┐                                             │    │
│  │  │ ApplicationHelper  │                                             │    │
│  │  │ (retrieval.py)     │                                             │    │
│  │  │                    │                                             │    │
│  │  │ - Documents List   │                                             │    │
│  │  │ - Process Steps    │                                             │    │
│  │  │ - Office Finder    │                                             │    │
│  │  └────────────────────┘                                             │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                       Memory System (memory.py)                      │    │
│  │                                                                      │    │
│  │  ┌───────────────────┐  ┌───────────────────┐  ┌─────────────────┐  │    │
│  │  │ConversationMemory │  │ UserProfileMemory │  │  SessionMemory  │  │    │
│  │  │                   │  │                   │  │                 │  │    │
│  │  │ - Message History │  │ - User Attributes │  │ - Session State │  │    │
│  │  │ - Sliding Window  │  │ - Contradictions  │  │ - Temp Data     │  │    │
│  │  │ - Turn Tracking   │  │ - Confirmations   │  │ - Context       │  │    │
│  │  └───────────────────┘  └───────────────────┘  └─────────────────┘  │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              LLM Backend Layer                               │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                       LLM Client (llm/client.py)                     │    │
│  │                                                                      │    │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────┐  │    │
│  │  │  OpenAI Client  │  │ Anthropic Client│  │    Mock Client      │  │    │
│  │  │  (GPT-4o)       │  │  (Claude)       │  │   (Testing Only)    │  │    │
│  │  └─────────────────┘  └─────────────────┘  └─────────────────────┘  │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Component Details

### 1. User Interface Layer

#### CLI Interface (`main.py`)
- **Purpose**: Command-line voice interaction for development and testing
- **Features**:
  - Real-time audio recording with VAD
  - Console output with color coding
  - Language selection at startup
- **Decision Rationale**: CLI provides fastest iteration during development and works without network requirements

#### Gradio Web UI (`app.py`)
- **Purpose**: Browser-based interface for end users
- **Features**:
  - Audio input with microphone access
  - Text fallback input
  - Language dropdown (9 Indian languages)
  - Conversation history display
- **Decision Rationale**: Gradio enables rapid prototyping of ML interfaces and handles audio streaming automatically

#### FastAPI Server (`server.py`)
- **Purpose**: Production-ready REST API and WebSocket endpoints
- **Features**:
  - REST endpoints for all operations
  - WebSocket for real-time streaming
  - Session management
  - File upload for audio
- **Decision Rationale**: FastAPI provides high performance, automatic API documentation, and native async support

---

### 2. Voice Processing Layer

#### STT Module (`voice/stt.py`)

| Backend | Pros | Cons | Best For |
|---------|------|------|----------|
| **Whisper** | Free, offline, accurate | Slower, requires GPU | Development, privacy |
| **Google Cloud** | Fast, scalable | Paid, needs internet | Production |
| **Azure Speech** | Best Indian language support | Paid, needs internet | Production with Indian languages |

**Factory Pattern**: `STTFactory` creates appropriate backend based on configuration, allowing runtime switching.

```python
# Backend selection logic
if backend == "whisper":
    return WhisperSTT(model_size, language)
elif backend == "google":
    return GoogleSTT(language)
elif backend == "azure":
    return AzureSTT(language, subscription_key, region)
```

#### TTS Module (`voice/tts.py`)

| Backend | Pros | Cons | Best For |
|---------|------|------|----------|
| **Azure Neural** | Natural voices, many Indian languages | Paid | Production |
| **gTTS** | Free, simple | Less natural | Development, fallback |
| **pyttsx3** | Offline, free | Limited language support | Offline fallback |

**Fallback Chain**: TTS automatically falls back to alternatives if primary fails:
```
Azure Neural → gTTS → pyttsx3
```

#### Audio Processing (`voice/audio.py`)
- **AudioRecorder**: Uses `sounddevice` for cross-platform recording
- **VAD (Voice Activity Detection)**: Energy-based silence detection
- **StreamingProcessor**: Buffer management for real-time processing

---

### 3. Agent Core Layer

#### State Machine (`agent/core.py`)

```
IDLE ──────────────► LISTENING
  ▲                      │
  │                      ▼
  │                UNDERSTANDING
  │                      │
  │         ◄──── ERROR_RECOVERY
  │                      │
  │                      ▼
  │                  PLANNING
  │                      │
  │                      ▼
  │                 EXECUTING ◄────────┐
  │                      │              │
  │                      ▼              │
  │                 EVALUATING ────────┘
  │                      │         (needs replanning)
  │                      ▼
  └───────────────── RESPONDING
```

**Decision Rationale**: Explicit state machine provides:
- Clear debugging and logging
- Predictable behavior
- Easy error recovery
- State persistence capability

#### Planner (`agent/planner.py`)

**Responsibilities**:
1. Parse user intent from transcribed text
2. Create task list with dependencies
3. Map intents to appropriate tools

**Multi-language System Prompts**:
```python
SYSTEM_PROMPTS = {
    "mr": """तुम्ही एक सरकारी योजना सहाय्यक आहात...""",
    "hi": """आप एक सरकारी योजना सहायक हैं...""",
    "te": """మీరు ప్రభుత్వ పథకాల సహాయకులు...""",
    # ... other languages
}
```

#### Executor (`agent/executor.py`)

**Responsibilities**:
1. Execute tasks in order respecting dependencies
2. Call tools via ToolRegistry
3. Handle tool errors gracefully
4. Update AgentContext with results

**Dependency Resolution**:
```python
def get_ready_tasks(plan, completed):
    ready = []
    for task in plan.tasks:
        if task.id not in completed:
            if all(dep in completed for dep in task.dependencies):
                ready.append(task)
    return ready
```

#### Evaluator (`agent/evaluator.py`)

**Responsibilities**:
1. Check if task execution was successful
2. Detect contradictions in user input
3. Assess input quality and confidence
4. Decide if replanning is needed

**Contradiction Detection**:
```python
def detect_contradiction(old_value, new_value, field):
    if field in ["age", "income", "land_size"]:
        if abs(old_value - new_value) > threshold[field]:
            return Contradiction(field, old_value, new_value)
    return None
```

---

### 4. Tools & Memory Layer

#### Tool Registry (`agent/core.py`)

All tools inherit from `BaseTool` and implement:
```python
class BaseTool(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...
    
    @property
    @abstractmethod
    def description(self) -> str: ...
    
    @abstractmethod
    def run(self, **kwargs) -> Dict[str, Any]: ...
    
    def to_openai_schema(self) -> Dict: ...
```

**Registered Tools**:
| Tool | Purpose | Key Parameters |
|------|---------|----------------|
| `eligibility_checker` | Check scheme eligibility | age, income, occupation, etc. |
| `scheme_retriever` | Search for schemes | query, category |
| `application_helper` | Get application process | scheme_id |

#### Scheme Database (`tools/eligibility.py`)

10+ government schemes with structured eligibility criteria:

```python
SCHEMES = {
    "pm_kisan": {
        "name": "PM-KISAN",
        "name_local": {"mr": "पीएम किसान सन्मान निधी", ...},
        "benefit": "₹6000/year in 3 installments",
        "criteria": {
            "is_farmer": True,
            "land_size_max": 5.0,  # acres
        }
    },
    # ... more schemes
}
```

#### Memory System (`memory/memory.py`)

| Memory Type | Purpose | Retention |
|-------------|---------|-----------|
| **ConversationMemory** | Message history | Sliding window (20 turns) |
| **UserProfileMemory** | User attributes | Session-persistent |
| **SessionMemory** | Temporary data | Session only |

**Contradiction Tracking**:
```python
class UserProfileMemory:
    def update(self, field, value, source):
        if field in self.data:
            old = self.data[field]
            if old.value != value:
                self.contradictions.append(
                    Contradiction(field, old.value, value)
                )
        self.data[field] = ProfileEntry(value, source)
```

---

### 5. LLM Backend Layer

#### Client Abstraction (`llm/client.py`)

```python
class BaseLLMClient(ABC):
    @abstractmethod
    async def chat(self, messages, tools=None) -> str: ...
    
    @abstractmethod
    async def chat_with_tools(self, messages, tools) -> ToolCallResult: ...
```

**Implementations**:
- `OpenAIClient`: GPT-4o with function calling
- `AnthropicClient`: Claude with tool use
- `MockLLMClient`: Returns Marathi responses for testing

---

## Data Flow

### Voice Input → Response

```
1. Audio Input
   │
   ├─► VAD detects speech end
   │
   └─► Audio buffer captured

2. STT Processing
   │
   ├─► Audio → Text (Whisper/Google/Azure)
   │
   └─► Confidence score attached

3. Understanding
   │
   ├─► Low confidence? → Ask to repeat
   │
   └─► Entity extraction (LLM)

4. Planning
   │
   ├─► Map to tool calls
   │
   └─► Create task list with dependencies

5. Execution
   │
   ├─► Call tools in order
   │
   └─► Collect results

6. Evaluation
   │
   ├─► Check success
   │
   ├─► Needs replanning? → Back to Planning
   │
   └─► Contradictions? → Ask for confirmation

7. Response Generation
   │
   ├─► LLM generates response in target language
   │
   └─► Response text produced

8. TTS
   │
   ├─► Text → Audio (Azure/gTTS/pyttsx3)
   │
   └─► Audio played to user
```

---

## Design Decisions

### 1. Why State Machine over Simple Loop?

| Aspect | State Machine | Simple Loop |
|--------|---------------|-------------|
| Error Recovery | Can return to specific states | Must restart |
| Debugging | Clear state transitions | Opaque control flow |
| Extensibility | Add states without rewrite | Major refactoring |
| Testing | Test individual states | Test entire flow |

### 2. Why Multiple STT/TTS Backends?

- **Reliability**: Fallback when one service fails
- **Cost**: Use free options for development
- **Privacy**: Offline options for sensitive data
- **Quality**: Different services excel at different languages

### 3. Why Separate Planner-Executor-Evaluator?

Based on the ReAct (Reasoning + Acting) pattern:
- **Separation of Concerns**: Each component has single responsibility
- **Replanning**: Evaluator can trigger replanning without restarting
- **Debugging**: Easy to see where issues occur
- **Extensibility**: Replace one component without affecting others

### 4. Why Memory Has Three Components?

| Memory | Purpose | Why Separate? |
|--------|---------|---------------|
| Conversation | Full dialogue | Needed for context |
| Profile | User attributes | Persists across sessions |
| Session | Temp data | Cleared each session |

### 5. Why Tool Registry Pattern?

- **Dynamic Registration**: Add tools at runtime
- **Uniform Interface**: All tools implement same API
- **Schema Generation**: Auto-generate OpenAI function schemas
- **Dependency Injection**: Easy testing with mock tools

---

## Error Handling Strategy

### Audio Errors
```
Low Confidence (<0.5) → Ask to repeat
No Speech Detected → Prompt user
Audio Too Short → Ask for more input
Audio Too Long → Process in chunks
```

### Tool Errors
```
Tool Not Found → Log and skip
Tool Execution Fail → Return error message
Tool Timeout → Cancel and inform user
```

### LLM Errors
```
Rate Limited → Exponential backoff
Invalid Response → Retry with clarification
Timeout → Use cached response or apologize
```

### Contradiction Handling
```
Contradiction Detected → Ask for confirmation
User Confirms New → Update profile
User Confirms Old → Keep existing
No Response → Keep old value (conservative)
```

---

## Performance Considerations

### Latency Optimization

| Component | Optimization |
|-----------|--------------|
| STT | Use streaming where possible |
| LLM | Request only needed fields |
| TTS | Cache common phrases |
| Tools | Parallel execution when independent |

### Memory Management

- Conversation window: 20 turns max (configurable)
- Audio buffer: 30 seconds max
- Profile data: Persist to disk periodically

### Scalability

- FastAPI with uvicorn workers for horizontal scaling
- Stateless design (state passed in requests)
- WebSocket for real-time but REST for stateless

---

## Security Considerations

1. **API Keys**: Stored in environment variables, never in code
2. **Audio Data**: Not persisted unless explicitly enabled
3. **User Data**: Profile cleared on session end
4. **Input Validation**: All inputs sanitized before LLM
5. **Rate Limiting**: Implemented at API level

---

## Future Enhancements

1. **Streaming Responses**: Real-time TTS as LLM generates
2. **Multi-Modal**: Add document upload for scheme forms
3. **Offline Mode**: Local LLM with reduced capabilities
4. **Analytics**: Track scheme queries for government insights
5. **Personalization**: Learn user preferences over time
