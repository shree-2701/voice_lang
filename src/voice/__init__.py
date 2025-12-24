"""
Voice Package
Contains speech-to-text, text-to-speech, and audio processing modules
"""
from .stt import (
    STTResult,
    BaseSTT,
    WhisperSTT,
    GoogleSTT,
    AzureSTT,
    STTFactory
)
from .tts import (
    TTSResult,
    BaseTTS,
    AzureTTS,
    GoogleTTS,
    Pyttsx3TTS,
    IndianLanguageTTS,
    TTSFactory
)
from .audio import (
    AudioConfig,
    AudioRecorder,
    AudioPlayer,
    StreamingAudioProcessor
)

__all__ = [
    # STT
    "STTResult",
    "BaseSTT",
    "WhisperSTT",
    "GoogleSTT",
    "AzureSTT",
    "STTFactory",
    # TTS
    "TTSResult",
    "BaseTTS",
    "AzureTTS",
    "GoogleTTS",
    "Pyttsx3TTS",
    "IndianLanguageTTS",
    "TTSFactory",
    # Audio
    "AudioConfig",
    "AudioRecorder",
    "AudioPlayer",
    "StreamingAudioProcessor"
]
