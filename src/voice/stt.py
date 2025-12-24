"""
Speech-to-Text Module
Supports multiple STT backends for Indian languages
"""
import os
import io
import wave
import asyncio
import tempfile
from abc import ABC, abstractmethod
from typing import Optional, Tuple, Dict, Any, List
from pathlib import Path
import shutil
import glob
import numpy as np
import importlib

from ..config import settings, WHISPER_LANGUAGE_CODES


class STTResult:
    """Result from speech-to-text transcription"""
    
    def __init__(self, 
                 text: str, 
                 confidence: float = 1.0,
                 language: Optional[str] = None,
                 duration: float = 0.0,
                 alternatives: Optional[List[Dict[str, Any]]] = None):
        self.text = text
        self.confidence = confidence
        self.language = language
        self.duration = duration
        self.alternatives = alternatives or []
    
    def is_empty(self) -> bool:
        return not self.text or self.text.strip() == ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "confidence": self.confidence,
            "language": self.language,
            "duration": self.duration,
            "alternatives": self.alternatives
        }


class BaseSTT(ABC):
    """Base class for STT implementations"""
    
    @abstractmethod
    async def transcribe(self, 
                        audio_data: bytes, 
                        language: Optional[str] = None) -> STTResult:
        """Transcribe audio data to text"""
        pass
    
    @abstractmethod
    async def transcribe_file(self, 
                             file_path: str, 
                             language: Optional[str] = None) -> STTResult:
        """Transcribe audio file to text"""
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if the STT service is available"""
        pass


class WhisperSTT(BaseSTT):
    """
    OpenAI Whisper-based STT
    Supports all major Indian languages
    """
    
    def __init__(self, model_size: str = "medium"):
        self.model_size = model_size
        self.model: Any = None
        self._initialized = False
    
    def _initialize(self):
        """Lazy initialization of Whisper model"""
        if self._initialized:
            return

        self._ensure_ffmpeg_available()
        
        try:
            import whisper
            self.model = whisper.load_model(self.model_size)
            self._initialized = True
        except ImportError:
            raise RuntimeError(
                "Whisper not installed. Install with: pip install openai-whisper"
            )

    def _ensure_ffmpeg_available(self) -> None:
        """Ensure ffmpeg is discoverable (Whisper requires it for decoding)."""
        if shutil.which("ffmpeg"):
            return

        if os.name == "nt":
            # Common WinGet install location used by: winget install Gyan.FFmpeg
            patterns = [
                os.path.expandvars(
                    r"%LOCALAPPDATA%\\Microsoft\\WinGet\\Packages\\Gyan.FFmpeg_*\\ffmpeg-*\\bin\\ffmpeg.exe"
                ),
                os.path.expandvars(
                    r"%LOCALAPPDATA%\\Microsoft\\WinGet\\Packages\\Gyan.FFmpeg_*\\*\\bin\\ffmpeg.exe"
                ),
            ]

            for pattern in patterns:
                matches = glob.glob(pattern)
                if not matches:
                    continue
                ffmpeg_exe = matches[0]
                ffmpeg_dir = str(Path(ffmpeg_exe).parent)
                os.environ["PATH"] = ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")
                if shutil.which("ffmpeg"):
                    return

        raise RuntimeError(
            "FFmpeg கிடைக்கவில்லை (Whisper-க்கு இது தேவை). "
            "Windows: `winget install Gyan.FFmpeg` செய்து, VS Code/Terminal-ஐ ரீஸ்டார்ட் செய்யவும். "
            "(Error: ffmpeg not found in PATH)"
        )
    
    async def transcribe(self, 
                        audio_data: bytes, 
                        language: Optional[str] = None) -> STTResult:
        """Transcribe audio bytes"""
        self._initialize()
        
        # Save to temp file
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(audio_data)
            temp_path = f.name
        
        try:
            result = await self.transcribe_file(temp_path, language)
            return result
        finally:
            Path(temp_path).unlink(missing_ok=True)
    
    async def transcribe_file(self, 
                             file_path: str, 
                             language: Optional[str] = None) -> STTResult:
        """Transcribe audio file"""
        self._initialize()
        
        # Get language code.
        # Tamil-only UX requirement: force Whisper to transcribe as Tamil.
        # Auto-detect can misclassify short Tamil utterances as Hindi and output Devanagari.
        lang_code: Optional[str] = None
        if language:
            if language == "tamil":
                lang_code = WHISPER_LANGUAGE_CODES.get("tamil", "ta")
            else:
                lang_code = WHISPER_LANGUAGE_CODES.get(language, language)
        
        # Run in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        
        def _transcribe():
            options: Dict[str, Any] = {
                "fp16": False,
                "task": "transcribe",
            }
            if lang_code:
                options["language"] = lang_code
            assert self.model is not None
            result = self.model.transcribe(file_path, **options)
            return result
        
        result = await loop.run_in_executor(None, _transcribe)
        
        # Calculate confidence from segments
        segments = result.get("segments", [])
        avg_confidence = 1.0
        if segments:
            confidences = [
                s.get("no_speech_prob", 0) 
                for s in segments
            ]
            avg_confidence = 1.0 - (sum(confidences) / len(confidences))
        
        # Get duration
        duration = 0.0
        if segments:
            duration = segments[-1].get("end", 0.0)
        
        return STTResult(
            text=result.get("text", "").strip(),
            confidence=avg_confidence,
            language=result.get("language"),
            duration=duration
        )
    
    def is_available(self) -> bool:
        try:
            import whisper
            return True
        except ImportError:
            return False


class GoogleSTT(BaseSTT):
    """
    Google Cloud Speech-to-Text
    Excellent for Indian languages with good accuracy
    """
    
    def __init__(self):
        self.client: Any = None
        self._initialized = False
    
    def _initialize(self):
        if self._initialized:
            return
        
        try:
            speech = importlib.import_module("google.cloud.speech")
            self.client = speech.SpeechClient()
            self.speech = speech
            self._initialized = True
        except Exception:
            raise RuntimeError(
                "Google Cloud Speech not installed. "
                "Install with: pip install google-cloud-speech"
            )
    
    async def transcribe(self, 
                        audio_data: bytes, 
                        language: Optional[str] = None) -> STTResult:
        """Transcribe audio bytes using Google STT"""
        self._initialize()
        
        from ..config import LANGUAGE_CODES
        lang_code = LANGUAGE_CODES.get(language or "hindi", "hi-IN")
        
        loop = asyncio.get_event_loop()
        
        def _transcribe():
            assert self.client is not None
            audio = self.speech.RecognitionAudio(content=audio_data)
            config = self.speech.RecognitionConfig(
                encoding=self.speech.RecognitionConfig.AudioEncoding.LINEAR16,
                sample_rate_hertz=settings.sample_rate,
                language_code=lang_code,
                enable_automatic_punctuation=True,
                model="latest_long",
                use_enhanced=True,
                alternative_language_codes=[
                    "hi-IN",  # Hindi as fallback
                    "en-IN"   # English (Indian) as fallback
                ]
            )
            
            response = self.client.recognize(config=config, audio=audio)
            return response
        
        response = await loop.run_in_executor(None, _transcribe)
        
        if not response.results:
            return STTResult(text="", confidence=0.0, language=language)
        
        # Get best result
        best_result = response.results[0]
        best_alternative = best_result.alternatives[0]
        
        # Get alternatives
        alternatives = [
            {
                "text": alt.transcript,
                "confidence": alt.confidence
            }
            for alt in best_result.alternatives[1:4]  # Top 3 alternatives
        ]
        
        return STTResult(
            text=best_alternative.transcript,
            confidence=best_alternative.confidence,
            language=language,
            alternatives=alternatives
        )
    
    async def transcribe_file(self, 
                             file_path: str, 
                             language: Optional[str] = None) -> STTResult:
        """Transcribe audio file"""
        with open(file_path, "rb") as f:
            audio_data = f.read()
        return await self.transcribe(audio_data, language)
    
    def is_available(self) -> bool:
        try:
            importlib.import_module("google.cloud.speech")
            return True
        except Exception:
            return False


class AzureSTT(BaseSTT):
    """
    Azure Cognitive Services Speech-to-Text
    Good support for Indian languages
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
    
    async def transcribe(self, 
                        audio_data: bytes, 
                        language: Optional[str] = None) -> STTResult:
        """Transcribe audio bytes"""
        # Save to temp file and use file-based transcription
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(audio_data)
            temp_path = f.name
        
        try:
            return await self.transcribe_file(temp_path, language)
        finally:
            Path(temp_path).unlink(missing_ok=True)
    
    async def transcribe_file(self, 
                             file_path: str, 
                             language: Optional[str] = None) -> STTResult:
        """Transcribe audio file"""
        self._initialize()

        assert self.speech_config is not None
        
        from ..config import LANGUAGE_CODES
        lang_code = LANGUAGE_CODES.get(language or "hindi", "hi-IN")
        
        self.speech_config.speech_recognition_language = lang_code
        
        loop = asyncio.get_event_loop()
        
        def _transcribe():
            audio_config = self.speechsdk.AudioConfig(filename=file_path)
            recognizer = self.speechsdk.SpeechRecognizer(
                speech_config=self.speech_config,
                audio_config=audio_config
            )
            
            result = recognizer.recognize_once()
            return result
        
        result = await loop.run_in_executor(None, _transcribe)
        
        if result.reason == self.speechsdk.ResultReason.RecognizedSpeech:
            return STTResult(
                text=result.text,
                confidence=0.9,  # Azure doesn't provide confidence directly
                language=language
            )
        elif result.reason == self.speechsdk.ResultReason.NoMatch:
            return STTResult(
                text="",
                confidence=0.0,
                language=language
            )
        else:
            return STTResult(
                text="",
                confidence=0.0,
                language=language
            )
    
    def is_available(self) -> bool:
        try:
            importlib.import_module("azure.cognitiveservices.speech")
            return settings.azure_speech_key is not None
        except Exception:
            return False


class STTFactory:
    """Factory for creating STT instances"""
    
    @staticmethod
    def create(backend: str = "whisper") -> BaseSTT:
        """Create an STT instance based on backend type"""
        backends = {
            "whisper": WhisperSTT,
            "google": GoogleSTT,
            "azure": AzureSTT
        }
        
        if backend not in backends:
            raise ValueError(f"Unknown STT backend: {backend}")
        
        stt_class = backends[backend]
        stt = stt_class()
        
        if not stt.is_available():
            # Fallback to Whisper
            print(f"Warning: {backend} STT not available, falling back to Whisper")
            return WhisperSTT()
        
        return stt
    
    @staticmethod
    def get_best_available() -> BaseSTT:
        """Get the best available STT backend"""
        # Priority: Azure > Google > Whisper
        for backend in ["azure", "google", "whisper"]:
            try:
                stt = STTFactory.create(backend)
                if stt.is_available():
                    return stt
            except:
                continue
        
        # Final fallback
        return WhisperSTT()
