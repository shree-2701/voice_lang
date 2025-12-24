"""
Main Voice Interface
End-to-end voice interaction loop for the government scheme agent
"""
import asyncio
import uuid
from typing import Optional, Dict, Any, Callable
from datetime import datetime
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.live import Live
from rich.spinner import Spinner

from .config import settings
from .agent import VoiceAgent, ToolRegistry, AgentState
from .tools import EligibilityChecker, SchemeRetriever, ApplicationHelper
from .voice import STTFactory, TTSFactory, AudioRecorder, AudioPlayer, AudioConfig
from .memory import MemoryManager, SessionMemory
from .llm import LLMClientFactory

console = Console()


class VoiceInterface:
    """
    Main voice interface for the government scheme agent
    Handles complete voice-to-voice interaction loop
    """
    
    def __init__(self, language: str = "marathi"):
        self.language = language
        self.memory_manager = MemoryManager()
        
        # Initialize components
        self._setup_components()
        
        # State
        self.current_session_id: Optional[str] = None
        self.is_running = False
        
        # Callbacks
        self.on_listening_start: Optional[Callable] = None
        self.on_listening_end: Optional[Callable] = None
        self.on_processing: Optional[Callable] = None
        self.on_speaking: Optional[Callable] = None
        self.on_error: Optional[Callable] = None
    
    def _setup_components(self):
        """Initialize all components"""
        # LLM Client
        self.llm_client = LLMClientFactory.create_from_settings()
        
        # Tool Registry
        self.tool_registry = ToolRegistry()
        self.tool_registry.register(EligibilityChecker())
        self.tool_registry.register(SchemeRetriever())
        self.tool_registry.register(ApplicationHelper())
        
        # Agent
        self.agent = VoiceAgent(
            llm_client=self.llm_client,
            tool_registry=self.tool_registry,
            language=self.language
        )
        
        # Voice components
        self.stt = STTFactory.get_best_available()
        self.tts = TTSFactory.get_best_available()
        self.recorder = AudioRecorder(AudioConfig(
            sample_rate=settings.sample_rate,
            channels=settings.audio_channels
        ))
        self.player = AudioPlayer(sample_rate=settings.sample_rate)
    
    def start_session(self) -> str:
        """Start a new interaction session"""
        session_id = self.agent.create_session()
        self.current_session_id = session_id
        self.memory_manager.create_session(session_id, self.language)
        
        console.print(Panel(
            f"[green]नवीन सत्र सुरू झाले[/green]\nSession ID: {session_id}",
            title="सत्र / Session",
            border_style="green"
        ))
        
        return session_id
    
    async def process_voice_input(self) -> Dict[str, Any]:
        """
        Complete voice input processing cycle:
        1. Record audio
        2. Transcribe to text
        3. Process with agent
        4. Synthesize response
        5. Play audio
        """
        if not self.current_session_id:
            self.start_session()

        assert self.current_session_id is not None
        
        session = self.memory_manager.get_session(self.current_session_id)
        assert session is not None
        
        try:
            # Step 1: Record audio
            console.print("\n[bold cyan]🎤 बोला... / Speak...[/bold cyan]")
            
            if self.on_listening_start:
                self.on_listening_start()
            
            audio_data = await self.recorder.record_with_vad(
                on_speech_start=lambda: console.print("[yellow]ऐकत आहे...[/yellow]"),
                on_speech_end=lambda: console.print("[green]✓ ऐकले[/green]")
            )
            
            if self.on_listening_end:
                self.on_listening_end()
            
            if not audio_data:
                return {"error": "No audio recorded", "text": ""}
            
            # Step 2: Transcribe
            console.print("[cyan]🔄 समजून घेत आहे...[/cyan]")
            
            if self.on_processing:
                self.on_processing()
            
            stt_result = await self.stt.transcribe(audio_data, self.language)
            
            if stt_result.is_empty():
                error_msg = "मला ऐकू आले नाही. कृपया पुन्हा बोला."
                await self._speak(error_msg)
                return {"error": "Empty transcription", "text": ""}
            
            console.print(Panel(
                f"[white]{stt_result.text}[/white]\n"
                f"[dim]Confidence: {stt_result.confidence:.2f}[/dim]",
                title="🗣️ तुम्ही म्हणालात / You said",
                border_style="blue"
            ))
            
            # Update memory
            session.add_user_message(
                stt_result.text,
                audio_confidence=stt_result.confidence
            )
            
            # Step 3: Process with agent
            console.print("[cyan]🤔 विचार करत आहे...[/cyan]")
            
            response = await self.agent.process_input(
                self.current_session_id,
                stt_result.text,
                stt_result.confidence
            )
            
            response_text = response.get("text", "")
            
            # Update memory
            session.add_assistant_message(response_text)
            
            # Display response
            console.print(Panel(
                f"[green]{response_text}[/green]",
                title="🤖 उत्तर / Response",
                border_style="green"
            ))
            
            # Display eligible schemes if any
            if response.get("eligible_schemes"):
                schemes_text = "\n".join([
                    f"• {s.get('name', s)}" 
                    for s in response["eligible_schemes"][:5]
                ])
                console.print(Panel(
                    schemes_text,
                    title="📋 पात्र योजना / Eligible Schemes",
                    border_style="yellow"
                ))
            
            # Step 4 & 5: Synthesize and play
            if response_text:
                await self._speak(response_text)
            
            return {
                "user_text": stt_result.text,
                "user_confidence": stt_result.confidence,
                "response_text": response_text,
                "response_type": response.get("type"),
                "eligible_schemes": response.get("eligible_schemes", []),
                "requires_input": response.get("requires_input", False)
            }
            
        except Exception as e:
            error_msg = f"त्रुटी आली: {str(e)}"
            console.print(f"[red]Error: {e}[/red]")
            
            if self.on_error:
                self.on_error(e)
            
            # Try to speak error message
            try:
                await self._speak("माफ करा, काहीतरी चूक झाली. कृपया पुन्हा प्रयत्न करा.")
            except:
                pass
            
            return {"error": str(e), "text": ""}
    
    async def process_text_input(self, text: str) -> Dict[str, Any]:
        """Process text input (for testing without microphone)"""
        if not self.current_session_id:
            self.start_session()

        assert self.current_session_id is not None
        
        session = self.memory_manager.get_session(self.current_session_id)
        assert session is not None
        
        console.print(Panel(
            f"[white]{text}[/white]",
            title="💬 तुमचा संदेश / Your message",
            border_style="blue"
        ))
        
        # Update memory
        session.add_user_message(text)
        
        # Process with agent
        console.print("[cyan]🤔 विचार करत आहे...[/cyan]")
        
        response = await self.agent.process_input(
            self.current_session_id,
            text,
            1.0  # Full confidence for text input
        )
        
        response_text = response.get("text", "")
        
        # Update memory
        session.add_assistant_message(response_text)
        
        # Display response
        console.print(Panel(
            f"[green]{response_text}[/green]",
            title="🤖 उत्तर / Response",
            border_style="green"
        ))
        
        # Speak response
        if response_text:
            await self._speak(response_text)
        
        return {
            "user_text": text,
            "response_text": response_text,
            "response_type": response.get("type"),
            "eligible_schemes": response.get("eligible_schemes", []),
            "requires_input": response.get("requires_input", False)
        }
    
    async def _speak(self, text: str):
        """Synthesize and play text"""
        if self.on_speaking:
            self.on_speaking()
        
        console.print("[cyan]🔊 बोलत आहे...[/cyan]")
        
        try:
            tts_result = await self.tts.synthesize(text, self.language)
            await self.player.play_bytes_async(tts_result.audio_data, tts_result.format)
        except Exception as e:
            console.print(f"[yellow]TTS Error: {e}[/yellow]")
    
    async def run_interactive_loop(self):
        """Run the main interactive voice loop"""
        self.is_running = True
        self.start_session()
        
        # Greeting
        greeting = self._get_greeting()
        console.print(Panel(
            f"[green]{greeting}[/green]",
            title="🙏 स्वागत / Welcome",
            border_style="green"
        ))
        await self._speak(greeting)
        
        while self.is_running:
            try:
                result = await self.process_voice_input()
                
                # Check for exit commands
                user_text = result.get("user_text", "").lower()
                if any(word in user_text for word in ["बंद करा", "थांबा", "exit", "quit", "बाय"]):
                    farewell = "धन्यवाद! तुमचा दिवस शुभ जावो."
                    console.print(f"\n[green]{farewell}[/green]")
                    await self._speak(farewell)
                    self.is_running = False
                    break
                
                # Small pause between interactions
                await asyncio.sleep(0.5)
                
            except KeyboardInterrupt:
                console.print("\n[yellow]Stopping...[/yellow]")
                self.is_running = False
                break
            except Exception as e:
                console.print(f"[red]Error in loop: {e}[/red]")
                await asyncio.sleep(1)
    
    def _get_greeting(self) -> str:
        """Get greeting message in current language"""
        greetings = {
            "marathi": "नमस्कार! मी तुमचा सरकारी योजना सहाय्यक आहे. मी तुम्हाला योग्य योजना शोधण्यात आणि अर्ज करण्यात मदत करतो. तुम्हाला कोणत्या प्रकारच्या योजनेची माहिती हवी आहे?",
            "hindi": "नमस्ते! मैं आपका सरकारी योजना सहायक हूं। मैं आपको सही योजना खोजने और आवेदन करने में मदद करता हूं। आपको किस प्रकार की योजना की जानकारी चाहिए?",
            "telugu": "నమస్కారం! నేను మీ ప్రభుత్వ పథకాల సహాయకుడిని. మీకు సరైన పథకాన్ని కనుగొని దరఖాస్తు చేయడంలో సహాయపడతాను. మీకు ఏ రకమైన పథకం గురించి సమాచారం కావాలి?",
            "tamil": "வணக்கம்! நான் உங்கள் அரசு திட்ட உதவியாளர். சரியான திட்டத்தைக் கண்டறிந்து விண்ணப்பிக்க உதவுகிறேன். எந்த வகையான திட்டம் பற்றிய தகவல் வேண்டும்?",
            "bengali": "নমস্কার! আমি আপনার সরকারি প্রকল্প সহায়ক। আমি আপনাকে সঠিক প্রকল্প খুঁজে বের করতে এবং আবেদন করতে সাহায্য করি। আপনার কোন ধরনের প্রকল্পের তথ্য দরকার?"
        }
        return greetings.get(self.language, greetings["hindi"])
    
    def get_agent_state(self) -> AgentState:
        """Get current agent state"""
        return self.agent.get_state()
    
    def get_session_context(self) -> Optional[Dict[str, Any]]:
        """Get current session context"""
        if self.current_session_id:
            session = self.memory_manager.get_session(self.current_session_id)
            if session:
                return session.get_full_context()
        return None
    
    def end_session(self):
        """End current session"""
        if self.current_session_id:
            self.agent.end_session(self.current_session_id)
            self.memory_manager.end_session(self.current_session_id)
            self.current_session_id = None
        self.is_running = False


async def main():
    """Main entry point for voice interface"""
    console.print(Panel(
        "[bold green]सरकारी योजना सहाय्यक[/bold green]\n"
        "Government Scheme Assistant\n\n"
        "[dim]Voice-First Agentic AI System[/dim]",
        title="🇮🇳 स्वागत / Welcome",
        border_style="green"
    ))
    
    # Get language preference
    console.print("\nभाषा निवडा / Select Language:")
    console.print("1. मराठी (Marathi)")
    console.print("2. हिंदी (Hindi)")
    console.print("3. తెలుగు (Telugu)")
    console.print("4. தமிழ் (Tamil)")
    console.print("5. বাংলা (Bengali)")
    
    try:
        choice = input("\nEnter choice (1-5) [default: 1]: ").strip() or "1"
        languages = {
            "1": "marathi",
            "2": "hindi",
            "3": "telugu",
            "4": "tamil",
            "5": "bengali"
        }
        language = languages.get(choice, "marathi")
    except:
        language = "marathi"
    
    console.print(f"\n[green]Selected: {language}[/green]\n")
    
    # Create and run interface
    interface = VoiceInterface(language=language)
    
    try:
        await interface.run_interactive_loop()
    except KeyboardInterrupt:
        console.print("\n[yellow]Goodbye![/yellow]")
    finally:
        interface.end_session()


if __name__ == "__main__":
    asyncio.run(main())
