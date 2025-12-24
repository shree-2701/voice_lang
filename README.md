# 🇮🇳 அரசுத் திட்ட உதவியாளர் (Government Scheme Voice Assistant)

A **voice-first** assistant that helps users find Indian government schemes and quickly understand **benefits + how to apply** in **Tamil**.

## 🎯 Project Overview

This project focuses on a stable, minimal pipeline:
- **Tamil-only** UI (Gradio)
- **Voice input** via local Whisper STT (forced to Tamil mode)
- **Local LLM** via Ollama (no API key required) for short localization/translation
- **Local scheme lookup** and short “how to apply” guidance
- **Strict Input Guardrails**: Rejects non-Tamil input to ensure consistent experience.

## 🏗️ Architecture (Current)

```
┌─────────────────────────────────────────────────────────────────┐
│                     Voice Interface Layer                        │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐  │
│  │  Audio   │───▶│   STT    │───▶│ Assistant│───▶│   TTS    │  │
│  │ Recorder │    │ (Whisper)│    │ (Simple) │    │ (Azure/  │  │
│  │          │    │          │    │          │    │  gTTS)   │  │
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                        Tool Layer                                │
│  ┌──────────────────┐  ┌──────────────────┐                     │
│  │ Eligibility      │  │ Scheme           │                     │
│  │ Checker          │  │ Retriever        │                     │
│  │                  │  │                  │                     │
│  │ • Profile Match  │  │ • Keyword Search │                     │
│  │ • Criteria Check │  │ • Category Filter│                     │
│  │ • Score Calc     │  │ • State Filter   │                     │
│  └──────────────────┘  └──────────────────┘                     │
│  ┌──────────────────┐                                           │
│  │ Application      │                                           │
│  │ Helper           │                                           │
│  │                  │                                           │
│  │ • Documents List │                                           │
│  │ • Process Steps  │                                           │
│  │ • Office Finder  │                                           │
│  └──────────────────┘                                           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
```

## 🧠 Memory & State Management

The system employs a dual-layer memory architecture to ensure context retention while maintaining deterministic reliability.

### 1. Session Layer (Short-term)
Managed by `AssistantSession` in `src/simple_assistant.py`. This layer persists only for the duration of the user interaction session.
- **Context Tracking:** Remembers the currently selected language (`tamil`/`english`) and the last set of scheme suggestions.
- **Flow State:** Maintains the position in the "Eligibility Checklist" (e.g., "Question 2 of 5: Do you have an Income Certificate?").
- **Slot Filling:** Temporarily stores user answers (Yes/No) to eligibility criteria to determine final qualification.
- **Reset Triggers:** Automatically clears state upon completion of a flow, explicit "Nandri/Vanakkam", or switching to a new scheme.

### 2. Knowledge Layer (Long-term)
Managed by `SchemeRetriever` and static localization dictionaries.
- **Static Database:** Contains hardcoded definitions for 10+ core government schemes (PM Kisan, PMAY, etc.).
- **Localization Memory:** Maps English scheme IDs to Tamil display names (`TA_SCHEME_NAMES`) and translates technical terms (Benefits, Documents) into natural Tamil phrasing.
- **Fuzzy Index:** Uses `difflib` and phonetic normalization to retrieve schemes even when input contains spelling errors (e.g., "ஆவாச்" -> "ஆவாஸ்").

### 3. Agent Memory (Advanced/Future)
Located in `src/memory/`, this module contains the infrastructure for a more complex agentic memory (not currently active in the Simple Assistant):
- **Conversation History:** Sliding window of recent turns with summarization.
- **Entity Extraction:** Structured storage of user details (Name, Age, Income) extracted from conversation.
- **Confidence Scoring:** Tracks the reliability of inferred information.

## 📁 Project Structure

```
Voice/
├── src/
│   ├── __init__.py
│   ├── config.py              # Configuration and settings
│   ├── simple_assistant.py     # Simplified scheme assistant (current)
│   ├── main.py                # Main voice interface
│   │
│   ├── agent/                 # Agentic framework
│   │   ├── __init__.py
│   │   ├── core.py            # State machine, tools, context
│   │   ├── planner.py         # Plan creation and revision
│   │   ├── executor.py        # Task execution
│   │   ├── evaluator.py       # Result evaluation
│   │   └── orchestrator.py    # Main agent coordinator
│   │
│   ├── voice/                 # Voice processing
│   │   ├── __init__.py
│   │   ├── stt.py             # Speech-to-Text (Whisper, Google, Azure)
│   │   ├── tts.py             # Text-to-Speech (Azure, gTTS)
│   │   └── audio.py           # Audio recording and playback
│   │
│   ├── tools/                 # Agent tools
│   │   ├── __init__.py
│   │   ├── eligibility.py     # Eligibility checking tool
│   │   └── retrieval.py       # Scheme retrieval tool
│   │
│   ├── memory/                # Memory management
│   │   ├── __init__.py
│   │   └── memory.py          # Conversation and profile memory
│   │
│   └── llm/                   # LLM integration
│       ├── __init__.py
│       └── client.py          # OpenAI/Anthropic clients
│
├── server.py                  # FastAPI server
├── app.py                     # Gradio web interface
├── requirements.txt           # Dependencies
├── .env.example               # Environment variables template
└── README.md                  # This file
```

## � Quick Start (Windows)

### 1. Prerequisites

- Python 3.10+
- Microphone (for voice input)
- Ollama (local LLM): https://ollama.com
- FFmpeg (required for Whisper audio decoding)

### 2. Installation

```bash
# Clone or navigate to the project
cd Voice

# Create virtual environment
python -m venv venv

# Activate (Windows)
.\venv\Scripts\activate

# Activate (Linux/Mac)
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configuration

```bash
# Copy example environment file
cp .env.example .env

# Edit .env with your API keys
notepad .env  # Windows
# or
nano .env     # Linux/Mac
```

Recommended environment variables (no API keys required):
```env
DEFAULT_LANGUAGE=tamil
FALLBACK_LANGUAGE=english
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2
```

### 4. Run the Application

**Option A: Command Line Interface**
```bash
python -m src.main
```

**Option B: Web Interface (Gradio)**
```bash
python app.py
# Open http://localhost:7860 in browser
```

**Option C: API Server (FastAPI)**
```bash
python server.py
# API available at http://localhost:8000
# Docs at http://localhost:8000/docs
```

## 🗣️ Supported Languages

| Language | Code | STT | TTS | Status |
|----------|------|-----|-----|--------|
| தமிழ் (Tamil) | ta-IN | ✅ | ✅ | **Active** |
| English | en-IN | ⚠️ | ✅ | Disabled (UI enforced) |
| Others | - | - | - | Future Scope |

## 🔧 Agent Tools

### 1. Eligibility Checker
Checks user eligibility for government schemes based on their profile.

**Parameters:**
- age, income, gender, caste_category
- state, occupation, education
- is_farmer, is_bpl, is_widow, is_disabled
- land_size, family_size

### 2. Scheme Retriever
Searches and retrieves relevant government schemes.

**Parameters:**
- query: Search query in any language
- category: agriculture, housing, health, education, pension, etc.
- state: Filter by state
- limit: Maximum results

### 3. Application Helper
Provides guidance on scheme application process.

**Actions:**
- get_documents: List required documents
- get_process: Application steps
- find_office: Nearby application offices

## 📋 Available Schemes (Sample)

The system includes mock data for 10+ schemes:

1. **PM-KISAN** - Financial assistance for farmers
2. **PMAY** - Affordable housing
3. **Mahatma Jyotirao Phule Jan Arogya Yojana** - Health insurance (Maharashtra)
4. **Widow Pension** - Monthly pension for widows
5. **Disability Pension** - Support for disabled persons
6. **PM Jan Dhan Yojana** - Zero balance bank accounts
7. **PM Suraksha Bima Yojana** - Accident insurance
8. **SC Scholarship** - Education support for SC students
9. **Ladki Bahin Yojana** - Women's welfare (Maharashtra)
10. **Old Age Pension** - Support for senior citizens

## 🧪 Testing

### Manual Testing

```bash
# Test eligibility checker
python -c "
import asyncio
from src.tools import EligibilityChecker

async def test():
    checker = EligibilityChecker()
    result = await checker.execute(
        age=35,
        income=50000,
        is_farmer=True,
        state='Maharashtra'
    )
    print(result)

asyncio.run(test())
"
```

### Example Conversations

**Successful Flow:**
```
User: எனக்கு விவசாய திட்டங்கள் வேண்டும்
Agent: தொடர்புடைய திட்டங்கள்:
       - பிரதான் மந்திரி கிசான் சம்மான் நிதி
       ஒரு திட்டத்தின் பெயரை பேசிச் சொல்லுங்கள்...
User: பிரதான் மந்திரி கிசான் சம்மான் நிதி
Agent: திட்டம்: பிரதான் மந்திரி கிசான் சம்மான் நிதி
       பயன்கள்: ஆண்டுக்கு ₹6000...
       ஆவணம் சரிபார்ப்பு (1/3): உங்களிடம் 'ஆதார் அட்டை' உள்ளதா? ஆம் அல்லது இல்லை
User: ஆம்
...
```

**Acronym Handling:**
```
User: PMAY (spoken as "பி யம ய வை")
Agent: (Detects 'Pradhan Mantri Awas Yojana')
       திட்டம்: பிரதான் மந்திரி ஆவாஸ் யோஜனா
       பயன்கள்: ₹2.5 லட்சம் வரை மானியம்...
```

**Error Recovery:**
```
User: [English speech] "I want housing scheme"
Agent: தமிழில் மட்டும் பேசுங்கள். உதாரணம்: 'பிரதான் மந்திரி ஆவாஸ் யோஜனா'...
```

## 📊 API Endpoints

### REST API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Health check |
| `/session/create` | POST | Create new session |
| `/session/{id}` | DELETE | End session |
| `/session/{id}/state` | GET | Get session state |
| `/chat/text` | POST | Process text input |
| `/chat/voice` | POST | Process voice input |
| `/tts` | POST | Text-to-speech |
| `/stt` | POST | Speech-to-text |
| `/schemes` | GET | List schemes |
| `/eligibility/check` | POST | Check eligibility |

### WebSocket

Connect to `/ws/{session_id}` for real-time voice interaction.

## 🎥 Demo Video Structure

For your 5-7 minute demo video:

1. **Introduction (30s)**
   - Show the architecture diagram
   - Explain the voice-first approach

2. **Tamil-Only Interface (30s)**
   - Show the clean Tamil UI
   - Demonstrate strict input guardrails (rejecting English)

3. **Happy Path (2min)**
   - User asks for "Housing" (வீடு)
   - Agent suggests PMAY
   - User selects PMAY
   - Agent walks through document checklist (Yes/No)
   - Agent provides final application steps

4. **Robustness (1min)**
   - Speak "PMAY" (acronym) -> System detects "Pradhan Mantri Awas Yojana"
   - Speak with minor spelling mistakes -> System fuzzy matches correctly

5. **Conclusion (30s)**
   - Summarize capabilities
   - Show code structure

## 📝 Evaluation Transcript

See `docs/evaluation_transcript.md` for detailed interaction logs.

## 🔒 Security Notes

- API keys should never be committed to version control
- Use environment variables for all secrets
- Audio data is processed in memory and not stored permanently

## 📄 License

This project is for educational/evaluation purposes.

## 🤝 Contributing

This is a hackathon submission. For questions, please refer to the documentation.

---

Made with ❤️ for Indian citizens
