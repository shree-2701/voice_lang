"""Gradio Web Interface.

Simplified pipeline for stability:
- Voice -> STT -> text
- Text -> local scheme lookup + short guidance (optionally localized via local LLM)
- Response -> short TTS summary
"""
import asyncio
import tempfile
import re
from typing import Optional, Any
import os

import gradio as gr
import gradio.themes as gr_themes

from src.simple_assistant import SimpleSchemeAssistant
from src.voice import STTFactory, TTSFactory
from src.llm import LLMClientFactory


# Global state
class AppState:
    def __init__(self):
        self.llm_client: Any = None
        self.assistant: Optional[SimpleSchemeAssistant] = None
        self.stt: Any = None
        self.tts: Any = None
        self.language = "tamil"
        self.conversation_history = []
    
    def initialize(self, language: str = "tamil"):
        """Initialize all components"""
        # Force Tamil-only operation
        self.language = "tamil"
        
        # LLM Client
        self.llm_client = LLMClientFactory.create_from_settings()

        # Simple assistant
        self.assistant = SimpleSchemeAssistant(llm_client=self.llm_client, language="tamil")
        self.assistant.set_language("tamil")
        
        # Voice components
        self.stt = STTFactory.get_best_available()
        self.tts = TTSFactory.get_best_available()
        
        self.conversation_history = []
        
        return "✅ தயாராக உள்ளது"


state = AppState()


def _tamilize_user_text(text: str) -> str:
    """Ensure user transcript shown on screen is Tamil-only as much as possible."""
    t = (text or "").strip()
    if not t:
        return t

    try:
        from src.simple_assistant import _rewrite_phonetic_acronyms

        normalized = _rewrite_phonetic_acronyms(t)
        n = (normalized or "").lower()

        if "pmay" in n:
            return "பிரதான் மந்திரி ஆவாஸ் யோஜனா"
        if "pm kisan" in n or "pmkisan" in n:
            return "பிரதான் மந்திரி கிசான் சம்மான் நிதி"
    except Exception:
        pass

    return t


async def process_audio_async(audio_path: str, language: str):
    """Process audio input asynchronously"""
    if state.assistant is None or state.language != language or state.stt is None or state.tts is None:
        state.initialize(language)

    assert state.assistant is not None
    assert state.stt is not None
    assert state.tts is not None
    
    # Force Tamil-only UI/output
    language = "tamil"

    if audio_path is None:
        return None, "தயவு செய்து ஆடியோ பதிவு செய்யவும்.", state.conversation_history

    if isinstance(audio_path, str) and not os.path.exists(audio_path):
        return None, f"பிழை / Error: ஆடியோ கோப்பு கிடைக்கவில்லை: {audio_path}", state.conversation_history
    
    try:
        # Read audio file
        with open(audio_path, "rb") as f:
            audio_data = f.read()
        
        # Transcribe
        stt_result = await state.stt.transcribe(audio_data, language)

        # Enforce Tamil-only input: if Whisper detects English, ask the user to speak in Tamil.
        detected_lang = (getattr(stt_result, "language", None) or "").strip().lower()
        if detected_lang in {"en", "english"}:
            msg = (
                "தமிழில் மட்டும் பேசுங்கள்.\n"
                "உதாரணம்: 'பிரதான் மந்திரி ஆவாஸ் யோஜனா' அல்லது 'பிரதான் மந்திரி கிசான் சம்மான் நிதி'."
            )
            return None, msg, state.conversation_history
        
        if stt_result.is_empty():
            error_msg = "கேட்கவில்லை. தயவு செய்து மீண்டும் பேசுங்கள்."
            return None, error_msg, state.conversation_history
        
        user_text = _tamilize_user_text(stt_result.text)
        
        # Add to conversation
        state.conversation_history.append(("user", user_text))
        
        # Process with simple assistant
        response_text = await state.assistant.handle_text(user_text)
        
        # Add to conversation
        state.conversation_history.append(("assistant", response_text))
        
        # Synthesize full response so voice matches the text output
        tts_result = await state.tts.synthesize(response_text, language)
        
        # Save audio to temp file
        temp_path = tempfile.mktemp(suffix=f".{tts_result.format}")
        with open(temp_path, "wb") as f:
            f.write(tts_result.audio_data)
        
        # Format conversation for display
        formatted_history = format_conversation(state.conversation_history)
        
        return temp_path, formatted_history, state.conversation_history
        
    except Exception as e:
        error_msg = f"பிழை ({type(e).__name__}): {str(e)}"
        return None, error_msg, state.conversation_history


def process_audio(audio_path: str, language: str):
    """Wrapper for async audio processing"""
    return asyncio.run(process_audio_async(audio_path, "tamil"))


async def process_text_async(text: str, language: str):
    """Process text input asynchronously"""
    # Text input is not used in the voice-only UI, but keep it Tamil-only if called.
    language = "tamil"
    if state.assistant is None or state.language != language or state.tts is None:
        state.initialize("tamil")

    assert state.assistant is not None
    assert state.tts is not None
    
    if not text or not text.strip():
        return None, "தயவு செய்து பேசுங்கள்.", state.conversation_history
    
    try:
        # Add to conversation
        state.conversation_history.append(("user", text))
        
        # Process with simple assistant
        response_text = await state.assistant.handle_text(text)
        
        # Add to conversation
        state.conversation_history.append(("assistant", response_text))
        
        # Synthesize full response so voice matches the text output
        tts_result = await state.tts.synthesize(response_text, language)
        
        # Save audio
        temp_path = tempfile.mktemp(suffix=f".{tts_result.format}")
        with open(temp_path, "wb") as f:
            f.write(tts_result.audio_data)
        
        # Format conversation
        formatted_history = format_conversation(state.conversation_history)
        
        return temp_path, formatted_history, state.conversation_history
        
    except Exception as e:
        error_msg = f"பிழை: {str(e)}"
        return None, error_msg, state.conversation_history


def process_text(text: str, language: str):
    """Wrapper for async text processing"""
    return asyncio.run(process_text_async(text, language))


def format_conversation(history: list) -> str:
    """Format conversation history for display"""
    formatted = []
    for role, content in history:
        if role == "user":
            formatted.append(f"👤 **நீங்கள்:** {content}")
        else:
            formatted.append(f"🤖 **உதவியாளர்:** {content}")
    return "\n\n".join(formatted)


def shorten_for_tts(text: str, max_chars: int = 450) -> str:
    """Deprecated: retained for backward compatibility (not used)."""
    t = (text or "").strip()
    if len(t) > max_chars:
        return t[: max_chars - 3].rstrip() + "..."
    return t


def clear_conversation():
    """Clear conversation and reset session"""
    state.conversation_history = []
    return "", None, []


def get_agent_info():
    """Get current system information"""
    if state.assistant is None:
        return "System not initialized"

    stt_name = getattr(state.stt, "name", None) or state.stt.__class__.__name__ if state.stt is not None else "(none)"
    tts_name = getattr(state.tts, "name", None) or state.tts.__class__.__name__ if state.tts is not None else "(none)"
    llm_name = getattr(state.llm_client, "name", None) or state.llm_client.__class__.__name__ if state.llm_client is not None else "(none)"

    return f"""
## முறை: எளிய திட்ட உதவியாளர்
## மொழி: தமிழ்

### பின்னணி அமைப்புகள்
- **மொழி மாதிரி:** {llm_name}
- **குரல்→உரை:** {stt_name}
- **உரை→குரல்:** {tts_name}
"""


# Create Gradio interface
def create_interface():
    """Create the Gradio interface"""
    
    with gr.Blocks(
        title="அரசுத் திட்ட உதவியாளர்",
        theme=gr_themes.Soft(),
        css="""
        .container { max-width: 1200px; margin: auto; }
        .header { text-align: center; margin-bottom: 20px; }
        """
    ) as demo:
        
        gr.Markdown("""
        # 🇮🇳 அரசுத் திட்ட உதவியாளர்
        குரல் மூலம் அரசுத் திட்டங்கள் பற்றி தெரிந்துகொள்ளுங்கள்.

        ---
        """)
        
        with gr.Row():
            with gr.Column(scale=2):
                # Language selection
                language_dropdown = gr.Dropdown(
                    choices=[
                        ("தமிழ்", "tamil"),
                    ],
                    value="tamil",
                    label="மொழி",
                    interactive=False
                )
                
                # Conversation display
                conversation_display = gr.Markdown(
                    value="*உரையாடல் இங்கே தோன்றும்*",
                    label="உரையாடல்"
                )
                
                # Audio input
                audio_input = gr.Audio(
                    sources=["microphone"],
                    type="filepath",
                    label="🎤 பேசுங்கள்"
                )

                with gr.Row():
                    clear_btn = gr.Button("🗑️ அழி")
                
                # Audio output
                audio_output = gr.Audio(
                    label="🔊 பதில் ஆடியோ",
                    autoplay=True
                )
            
            with gr.Column(scale=1):
                gr.Markdown("### 📊 தகவல் / Info")
                gr.Markdown("### 📊 தகவல்")
                agent_info_display = gr.Markdown(value="*தொடங்க தயாராக உள்ளது*")
                refresh_info_btn = gr.Button("🔄 புதுப்பி")
                
                gr.Markdown("""
                ### 📋 உதாரண கேள்விகள்

                - "பிரதான் மந்திரி கிசான் சம்மான் நிதி"
                - "பிரதான் மந்திரி ஆவாஸ் யோஜனா"
                - "எனக்கு வீட்டு திட்டம் வேண்டும்"
                - "நான் விவசாயி"
                
                ---
                
                ### 📌 வழிமுறை

                1. மொழியைத் தேர்ந்தெடுக்கவும்
                2. மைக் மூலம் பேசுங்கள்
                3. திட்டத்தின் பயன்கள் + ஆவண சரிபார்ப்பு + விண்ணப்பிக்கும் படிகள் கிடைக்கும்
                """)
        
        # Hidden state for conversation history
        conversation_state = gr.State([])
        
        # Event handlers
        def on_audio_submit(audio, lang, history):
            audio_out, text_out, new_history = process_audio(audio, lang)
            return audio_out, text_out, new_history
        
        # Connect events
        audio_input.stop_recording(
            fn=on_audio_submit,
            inputs=[audio_input, language_dropdown, conversation_state],
            outputs=[audio_output, conversation_display, conversation_state]
        )
        
        clear_btn.click(
            fn=clear_conversation,
            outputs=[conversation_display, audio_output, conversation_state]
        )
        
        refresh_info_btn.click(
            fn=get_agent_info,
            outputs=[agent_info_display]
        )
        
        # Initialize on language change
        language_dropdown.change(
            fn=lambda lang: (state.initialize("tamil"), get_agent_info()),
            inputs=[language_dropdown],
            outputs=[conversation_display, agent_info_display]
        )
    
    return demo


def main():
    """Launch the Gradio interface"""
    demo = create_interface()
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=True,
        show_error=True
    )


if __name__ == "__main__":
    main()
