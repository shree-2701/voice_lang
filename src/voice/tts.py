"""
Text-to-Speech Module
Supports multiple TTS backends for Indian languages
"""
import io
import asyncio
import tempfile
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from pathlib import Path
import importlib

from ..config import settings, AZURE_VOICE_NAMES, LANGUAGE_CODES


class TTSResult:
    """Result from text-to-speech synthesis"""
    
    def __init__(self,
                 audio_data: bytes,
                 format: str = "wav",
                 sample_rate: int = 16000,
                 duration: float = 0.0):
        self.audio_data = audio_data
        self.format = format
        self.sample_rate = sample_rate
        self.duration = duration
    
    def save(self, file_path: str):
        """Save audio to file"""
        with open(file_path, "wb") as f:
            f.write(self.audio_data)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "format": self.format,
            "sample_rate": self.sample_rate,
            "duration": self.duration,
            "size_bytes": len(self.audio_data)
        }


class BaseTTS(ABC):
    """Base class for TTS implementations"""
    
    @abstractmethod
    async def synthesize(self, 
                        text: str, 
                        language: Optional[str] = None) -> TTSResult:
        """Synthesize text to speech"""
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if the TTS service is available"""
        pass


class AzureTTS(BaseTTS):
    """
    Azure Cognitive Services Text-to-Speech
    Best quality for Indian languages with neural voices
    """
    
    def __init__(self):
        self._initialized = False
        self.speech_config: Any = None
    
    def _initialize(self):
        if self._initialized:
            return
        
        try:
            speechsdk = importlib.import_module("azure.cognitiveservices.speech")
            self.speechsdk = speechsdk
            
            if not settings.azure_speech_key:
                raise ValueError("Azure Speech key not configured")
            
            self.speech_config = speechsdk.SpeechConfig(
                subscription=settings.azure_speech_key,
                region=settings.azure_speech_region
            )
            self._initialized = True
        except Exception:
            raise RuntimeError(
                "Azure Speech SDK not installed. "
                "Install with: pip install azure-cognitiveservices-speech"
            )
    
    async def synthesize(self, 
                        text: str, 
                        language: Optional[str] = None) -> TTSResult:
        """Synthesize text using Azure Neural TTS"""
        self._initialize()

        assert self.speech_config is not None
        
        # Get voice for language (Tamil/English only). Default to English if unspecified.
        voice_name = AZURE_VOICE_NAMES.get(language or "english", AZURE_VOICE_NAMES["english"])
        
        # Set output format
        self.speech_config.set_speech_synthesis_output_format(
            self.speechsdk.SpeechSynthesisOutputFormat.Audio16Khz32KBitRateMonoMp3
        )
        self.speech_config.speech_synthesis_voice_name = voice_name
        
        loop = asyncio.get_event_loop()
        
        def _synthesize():
            synthesizer = self.speechsdk.SpeechSynthesizer(
                speech_config=self.speech_config,
                audio_config=None  # Return audio data
            )
            
            result = synthesizer.speak_text_async(text).get()
            return result
        
        result = await loop.run_in_executor(None, _synthesize)
        
        if result.reason == self.speechsdk.ResultReason.SynthesizingAudioCompleted:
            return TTSResult(
                audio_data=result.audio_data,
                format="mp3",
                sample_rate=16000,
                duration=result.audio_duration.total_seconds() if result.audio_duration else 0.0
            )
        else:
            raise RuntimeError(f"TTS synthesis failed: {result.reason}")
    
    def is_available(self) -> bool:
        try:
            importlib.import_module("azure.cognitiveservices.speech")
            return settings.azure_speech_key is not None
        except Exception:
            return False


class GoogleTTS(BaseTTS):
    """
    gTTS (Google Text-to-Speech)
    Free and supports all Indian languages
    """
    
    def __init__(self):
        self._initialized = False
    
    def _initialize(self):
        if self._initialized:
            return
        
        try:
            from gtts import gTTS
            self.gTTS = gTTS
            self._initialized = True
        except ImportError:
            raise RuntimeError(
                "gTTS not installed. Install with: pip install gTTS"
            )
    
    async def synthesize(self, 
                        text: str, 
                        language: Optional[str] = None) -> TTSResult:
        """Synthesize text using gTTS"""
        self._initialize()
        
        # Map to gTTS language codes
        gtts_lang_map = {
            "tamil": "ta",
            "english": "en",
        }

        lang_code = gtts_lang_map.get(language or "english", "en")
        
        loop = asyncio.get_event_loop()
        
        def _synthesize():
            tts = self.gTTS(text=text, lang=lang_code, slow=False)
            
            # Save to bytes
            audio_buffer = io.BytesIO()
            tts.write_to_fp(audio_buffer)
            audio_buffer.seek(0)
            
            return audio_buffer.read()
        
        audio_data = await loop.run_in_executor(None, _synthesize)
        
        return TTSResult(
            audio_data=audio_data,
            format="mp3",
            sample_rate=24000  # gTTS uses 24kHz
        )
    
    def is_available(self) -> bool:
        try:
            from gtts import gTTS
            return True
        except ImportError:
            return False


class Pyttsx3TTS(BaseTTS):
    """
    pyttsx3 - Offline TTS
    Uses system voices, limited Indian language support
    """
    
    def __init__(self):
        self._initialized = False
        self.engine: Any = None
    
    def _initialize(self):
        if self._initialized:
            return
        
        try:
            import pyttsx3
            self.engine = pyttsx3.init()
            self._initialized = True
        except ImportError:
            raise RuntimeError(
                "pyttsx3 not installed. Install with: pip install pyttsx3"
            )
    
    async def synthesize(self, 
                        text: str, 
                        language: Optional[str] = None) -> TTSResult:
        """Synthesize text using pyttsx3"""
        self._initialize()
        assert self.engine is not None
        
        loop = asyncio.get_event_loop()
        
        def _synthesize():
            # Create temp file
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                temp_path = f.name
            
            self.engine.save_to_file(text, temp_path)
            self.engine.runAndWait()
            
            with open(temp_path, "rb") as f:
                audio_data = f.read()
            
            Path(temp_path).unlink(missing_ok=True)
            return audio_data
        
        audio_data = await loop.run_in_executor(None, _synthesize)
        
        return TTSResult(
            audio_data=audio_data,
            format="wav",
            sample_rate=22050
        )
    
    def is_available(self) -> bool:
        try:
            import pyttsx3
            return True
        except ImportError:
            return False


class IndianLanguageTTS(BaseTTS):
    """
    Specialized TTS for Indian languages
    Uses multiple backends with automatic fallback
    """
    
    def __init__(self, preferred_backend: str = "azure"):
        self.backends = []
        self._setup_backends(preferred_backend)
    
    def _setup_backends(self, preferred: str):
        """Setup TTS backends in order of preference"""
        backend_classes = {
            "azure": AzureTTS,
            "google": GoogleTTS,
            "pyttsx3": Pyttsx3TTS
        }
        
        # Add preferred backend first
        if preferred in backend_classes:
            try:
                backend = backend_classes[preferred]()
                if backend.is_available():
                    self.backends.append(backend)
            except:
                pass
        
        # Add other backends as fallback
        for name, cls in backend_classes.items():
            if name != preferred:
                try:
                    backend = cls()
                    if backend.is_available():
                        self.backends.append(backend)
                except:
                    pass
    
    async def synthesize(self, 
                        text: str, 
                        language: Optional[str] = None) -> TTSResult:
        """Synthesize using best available backend"""
        for backend in self.backends:
            try:
                return await backend.synthesize(text, language)
            except Exception as e:
                print(f"TTS backend failed: {e}")
                continue
        
        raise RuntimeError("No TTS backend available")
    
    def is_available(self) -> bool:
        return len(self.backends) > 0


class TTSFactory:
    """Factory for creating TTS instances"""
    
    @staticmethod
    def create(backend: str = "azure") -> BaseTTS:
        """Create a TTS instance based on backend type"""
        backends = {
            "azure": AzureTTS,
            "google": GoogleTTS,
            "pyttsx3": Pyttsx3TTS,
            "auto": IndianLanguageTTS
        }
        
        if backend not in backends:
            raise ValueError(f"Unknown TTS backend: {backend}")
        
        return backends[backend]()
    
    @staticmethod
    def get_best_available() -> BaseTTS:
        """Get the best available TTS with automatic fallback"""
        return IndianLanguageTTS()
