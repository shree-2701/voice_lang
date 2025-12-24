"""
FastAPI Server for Voice Agent
Provides REST API and WebSocket endpoints for voice interaction
"""
import asyncio
import uuid
import json
import base64
from typing import Optional, Dict, Any
from datetime import datetime

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
import io

from src.config import settings, SupportedLanguage
from src.agent import VoiceAgent, ToolRegistry, AgentState
from src.tools import EligibilityChecker, SchemeRetriever, ApplicationHelper
from src.voice import STTFactory, TTSFactory
from src.memory import MemoryManager
from src.llm import LLMClientFactory


# Initialize FastAPI app
app = FastAPI(
    title="Government Scheme Voice Agent",
    description="Voice-First Agentic AI for Government Scheme Assistance in Indian Languages",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global components
memory_manager = MemoryManager()
agents: Dict[str, VoiceAgent] = {}
stt = None
tts = None


def get_or_create_agent(session_id: str, language: str = "marathi") -> VoiceAgent:
    """Get existing agent or create new one"""
    if session_id not in agents:
        llm_client = LLMClientFactory.create_from_settings()
        tool_registry = ToolRegistry()
        tool_registry.register(EligibilityChecker())
        tool_registry.register(SchemeRetriever())
        tool_registry.register(ApplicationHelper())
        
        agent = VoiceAgent(
            llm_client=llm_client,
            tool_registry=tool_registry,
            language=language
        )
        agent.create_session()
        agents[session_id] = agent
        memory_manager.create_session(session_id, language)
    
    return agents[session_id]


# Request/Response Models
class TextRequest(BaseModel):
    text: str
    language: str = "marathi"
    session_id: Optional[str] = None


class SessionRequest(BaseModel):
    language: str = "marathi"


class SessionResponse(BaseModel):
    session_id: str
    language: str
    created_at: str


class AgentResponse(BaseModel):
    text: str
    type: str
    eligible_schemes: list = []
    next_steps: list = []
    requires_input: bool = False
    agent_state: str
    session_id: str


# REST Endpoints
@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "status": "running",
        "service": "Government Scheme Voice Agent",
        "version": "1.0.0",
        "supported_languages": [lang.value for lang in SupportedLanguage]
    }


@app.post("/session/create", response_model=SessionResponse)
async def create_session(request: SessionRequest):
    """Create a new session"""
    session_id = f"session_{uuid.uuid4().hex[:8]}"
    agent = get_or_create_agent(session_id, request.language)
    
    return SessionResponse(
        session_id=session_id,
        language=request.language,
        created_at=datetime.now().isoformat()
    )


@app.delete("/session/{session_id}")
async def end_session(session_id: str):
    """End a session"""
    if session_id in agents:
        del agents[session_id]
    memory_manager.end_session(session_id)
    
    return {"status": "session ended", "session_id": session_id}


@app.get("/session/{session_id}/state")
async def get_session_state(session_id: str):
    """Get current session state"""
    if session_id not in agents:
        raise HTTPException(status_code=404, detail="Session not found")
    
    agent = agents[session_id]
    session = memory_manager.get_session(session_id)
    
    return {
        "session_id": session_id,
        "agent_state": agent.get_state().value,
        "state_history": agent.get_state_history(),
        "context": session.get_full_context() if session else None
    }


@app.post("/chat/text", response_model=AgentResponse)
async def chat_text(request: TextRequest):
    """Process text input"""
    session_id = request.session_id or f"session_{uuid.uuid4().hex[:8]}"
    agent = get_or_create_agent(session_id, request.language)
    
    # Get or create agent session
    agent_session_id = list(agent.sessions.keys())[0] if agent.sessions else agent.create_session()
    
    # Process input
    response = await agent.process_input(
        agent_session_id,
        request.text,
        1.0  # Full confidence for text
    )
    
    return AgentResponse(
        text=response.get("text", ""),
        type=response.get("type", "response"),
        eligible_schemes=response.get("eligible_schemes", []),
        next_steps=response.get("next_steps", []),
        requires_input=response.get("requires_input", False),
        agent_state=agent.get_state().value,
        session_id=session_id
    )


@app.post("/chat/voice")
async def chat_voice(
    audio: UploadFile = File(...),
    language: str = Form("marathi"),
    session_id: Optional[str] = Form(None)
):
    """Process voice input and return voice response"""
    global stt, tts
    
    # Initialize STT/TTS if needed
    if stt is None:
        stt = STTFactory.get_best_available()
    if tts is None:
        tts = TTSFactory.get_best_available()
    
    session_id = session_id or f"session_{uuid.uuid4().hex[:8]}"
    agent = get_or_create_agent(session_id, language)
    agent_session_id = list(agent.sessions.keys())[0] if agent.sessions else agent.create_session()
    
    # Read audio data
    audio_data = await audio.read()
    
    # Transcribe
    stt_result = await stt.transcribe(audio_data, language)
    
    if stt_result.is_empty():
        return JSONResponse({
            "error": "Could not transcribe audio",
            "session_id": session_id
        }, status_code=400)
    
    # Process with agent
    response = await agent.process_input(
        agent_session_id,
        stt_result.text,
        stt_result.confidence
    )
    
    response_text = response.get("text", "")
    
    # Synthesize response
    tts_result = await tts.synthesize(response_text, language)
    
    # Return audio response
    return StreamingResponse(
        io.BytesIO(tts_result.audio_data),
        media_type=f"audio/{tts_result.format}",
        headers={
            "X-Transcribed-Text": stt_result.text,
            "X-Response-Text": response_text,
            "X-Confidence": str(stt_result.confidence),
            "X-Session-Id": session_id,
            "X-Agent-State": agent.get_state().value
        }
    )


@app.post("/tts")
async def text_to_speech(
    text: str = Form(...),
    language: str = Form("marathi")
):
    """Convert text to speech"""
    global tts
    
    if tts is None:
        tts = TTSFactory.get_best_available()
    
    tts_result = await tts.synthesize(text, language)
    
    return StreamingResponse(
        io.BytesIO(tts_result.audio_data),
        media_type=f"audio/{tts_result.format}"
    )


@app.post("/stt")
async def speech_to_text(
    audio: UploadFile = File(...),
    language: str = Form("marathi")
):
    """Convert speech to text"""
    global stt
    
    if stt is None:
        stt = STTFactory.get_best_available()
    
    audio_data = await audio.read()
    result = await stt.transcribe(audio_data, language)
    
    return {
        "text": result.text,
        "confidence": result.confidence,
        "language": result.language,
        "duration": result.duration
    }


@app.get("/schemes")
async def get_schemes(
    category: Optional[str] = None,
    state: Optional[str] = None,
    limit: int = 10
):
    """Get list of government schemes"""
    from src.tools.eligibility import GOVERNMENT_SCHEMES
    
    schemes = GOVERNMENT_SCHEMES
    
    if category:
        schemes = [s for s in schemes if s.get("category") == category]
    
    if state:
        schemes = [
            s for s in schemes 
            if not s.get("eligibility_criteria", {}).get("states") or
               state.lower() in [st.lower() for st in s.get("eligibility_criteria", {}).get("states", [])]
        ]
    
    return {
        "schemes": schemes[:limit],
        "total": len(schemes),
        "filters": {"category": category, "state": state}
    }


@app.post("/eligibility/check")
async def check_eligibility(profile: Dict[str, Any]):
    """Check eligibility for schemes"""
    checker = EligibilityChecker()
    result = await checker.execute(**profile)
    return result


# WebSocket for real-time voice interaction
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
    
    async def connect(self, websocket: WebSocket, session_id: str):
        await websocket.accept()
        self.active_connections[session_id] = websocket
    
    def disconnect(self, session_id: str):
        if session_id in self.active_connections:
            del self.active_connections[session_id]
    
    async def send_json(self, session_id: str, data: dict):
        if session_id in self.active_connections:
            await self.active_connections[session_id].send_json(data)


manager = ConnectionManager()


@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for real-time voice interaction"""
    global stt, tts
    
    if stt is None:
        stt = STTFactory.get_best_available()
    if tts is None:
        tts = TTSFactory.get_best_available()
    
    await manager.connect(websocket, session_id)
    
    # Get or create agent
    language = "marathi"  # Default, will be updated from first message
    agent = get_or_create_agent(session_id, language)
    agent_session_id = list(agent.sessions.keys())[0] if agent.sessions else agent.create_session()
    
    try:
        # Send welcome message
        await manager.send_json(session_id, {
            "type": "connected",
            "session_id": session_id,
            "agent_state": agent.get_state().value
        })
        
        while True:
            data = await websocket.receive_json()
            message_type = data.get("type")
            
            if message_type == "audio":
                # Process audio message
                audio_base64 = data.get("audio")
                language = data.get("language", "marathi")
                
                if audio_base64:
                    audio_bytes = base64.b64decode(audio_base64)
                    
                    # Transcribe
                    await manager.send_json(session_id, {
                        "type": "processing",
                        "status": "transcribing"
                    })
                    
                    stt_result = await stt.transcribe(audio_bytes, language)
                    
                    await manager.send_json(session_id, {
                        "type": "transcription",
                        "text": stt_result.text,
                        "confidence": stt_result.confidence
                    })
                    
                    if not stt_result.is_empty():
                        # Process with agent
                        await manager.send_json(session_id, {
                            "type": "processing",
                            "status": "thinking"
                        })
                        
                        response = await agent.process_input(
                            agent_session_id,
                            stt_result.text,
                            stt_result.confidence
                        )
                        
                        response_text = response.get("text", "")
                        
                        await manager.send_json(session_id, {
                            "type": "response",
                            "text": response_text,
                            "eligible_schemes": response.get("eligible_schemes", []),
                            "agent_state": agent.get_state().value
                        })
                        
                        # Synthesize response
                        await manager.send_json(session_id, {
                            "type": "processing",
                            "status": "speaking"
                        })
                        
                        tts_result = await tts.synthesize(response_text, language)
                        
                        await manager.send_json(session_id, {
                            "type": "audio_response",
                            "audio": base64.b64encode(tts_result.audio_data).decode(),
                            "format": tts_result.format
                        })
            
            elif message_type == "text":
                # Process text message
                text = data.get("text", "")
                language = data.get("language", "marathi")
                
                if text:
                    response = await agent.process_input(
                        agent_session_id,
                        text,
                        1.0
                    )
                    
                    response_text = response.get("text", "")
                    
                    await manager.send_json(session_id, {
                        "type": "response",
                        "text": response_text,
                        "eligible_schemes": response.get("eligible_schemes", []),
                        "agent_state": agent.get_state().value
                    })
                    
                    # Synthesize response
                    tts_result = await tts.synthesize(response_text, language)
                    
                    await manager.send_json(session_id, {
                        "type": "audio_response",
                        "audio": base64.b64encode(tts_result.audio_data).decode(),
                        "format": tts_result.format
                    })
            
            elif message_type == "ping":
                await manager.send_json(session_id, {"type": "pong"})
    
    except WebSocketDisconnect:
        manager.disconnect(session_id)
    except Exception as e:
        await manager.send_json(session_id, {
            "type": "error",
            "message": str(e)
        })
        manager.disconnect(session_id)


def run_server():
    """Run the FastAPI server"""
    import uvicorn
    uvicorn.run(
        "server:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug
    )


if __name__ == "__main__":
    run_server()
