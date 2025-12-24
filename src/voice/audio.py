"""
Audio Recording Module
Handles microphone input and audio stream management
"""
import asyncio
import queue
import threading
import wave
import io
import tempfile
from typing import Optional, Callable, Generator
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ..config import settings


@dataclass
class AudioConfig:
    """Audio configuration settings"""
    sample_rate: int = 16000
    channels: int = 1
    chunk_size: int = 1024
    format: str = "int16"
    silence_threshold: float = 0.01
    silence_duration: float = 1.5  # seconds of silence to stop recording
    max_duration: float = 30.0  # maximum recording duration


class AudioRecorder:
    """
    Handles audio recording from microphone
    Supports both push-to-talk and voice activity detection
    """
    
    def __init__(self, config: Optional[AudioConfig] = None):
        self.config = config or AudioConfig(
            sample_rate=settings.sample_rate,
            channels=settings.audio_channels
        )
        self._is_recording = False
        self._audio_queue = queue.Queue()
        self._frames = []
    
    def start_recording(self) -> bool:
        """Start recording audio from microphone"""
        if self._is_recording:
            return False
        
        try:
            import sounddevice as sd
            
            self._frames = []
            self._is_recording = True
            
            def audio_callback(indata, frames, time, status):
                if status:
                    print(f"Audio status: {status}")
                if self._is_recording:
                    self._audio_queue.put(indata.copy())
            
            self._stream = sd.InputStream(
                samplerate=self.config.sample_rate,
                channels=self.config.channels,
                dtype=self.config.format,
                blocksize=self.config.chunk_size,
                callback=audio_callback
            )
            self._stream.start()
            
            return True
            
        except ImportError:
            raise RuntimeError(
                "sounddevice not installed. Install with: pip install sounddevice"
            )
        except Exception as e:
            self._is_recording = False
            raise RuntimeError(f"Failed to start recording: {e}")
    
    def stop_recording(self) -> bytes:
        """Stop recording and return audio data"""
        if not self._is_recording:
            return b""
        
        self._is_recording = False
        
        if hasattr(self, "_stream"):
            self._stream.stop()
            self._stream.close()
        
        # Collect all frames from queue
        frames = []
        while not self._audio_queue.empty():
            frames.append(self._audio_queue.get())
        
        if not frames:
            return b""
        
        # Combine frames
        audio_data = np.concatenate(frames)
        
        # Convert to bytes (WAV format)
        return self._to_wav_bytes(audio_data)
    
    def _to_wav_bytes(self, audio_data: np.ndarray) -> bytes:
        """Convert numpy array to WAV bytes"""
        buffer = io.BytesIO()
        
        with wave.open(buffer, "wb") as wav_file:
            wav_file.setnchannels(self.config.channels)
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(self.config.sample_rate)
            wav_file.writeframes(audio_data.tobytes())
        
        buffer.seek(0)
        return buffer.read()
    
    async def record_with_vad(self, 
                             on_speech_start: Optional[Callable] = None,
                             on_speech_end: Optional[Callable] = None) -> bytes:
        """
        Record with Voice Activity Detection
        Automatically stops when silence is detected
        """
        try:
            import sounddevice as sd
        except ImportError:
            raise RuntimeError("sounddevice not installed")
        
        frames = []
        silence_frames = 0
        speech_started = False
        max_frames = int(self.config.max_duration * self.config.sample_rate / self.config.chunk_size)
        silence_threshold_frames = int(
            self.config.silence_duration * self.config.sample_rate / self.config.chunk_size
        )
        
        def process_frame(indata):
            nonlocal silence_frames, speech_started
            
            # Calculate RMS energy
            rms = np.sqrt(np.mean(indata ** 2))
            
            if rms > self.config.silence_threshold:
                if not speech_started:
                    speech_started = True
                    if on_speech_start:
                        on_speech_start()
                silence_frames = 0
                return True  # Keep recording
            else:
                if speech_started:
                    silence_frames += 1
                    if silence_frames >= silence_threshold_frames:
                        if on_speech_end:
                            on_speech_end()
                        return False  # Stop recording
                return True  # Keep recording
        
        # Recording loop
        with sd.InputStream(
            samplerate=self.config.sample_rate,
            channels=self.config.channels,
            dtype=self.config.format,
            blocksize=self.config.chunk_size
        ) as stream:
            frame_count = 0
            while frame_count < max_frames:
                data, _ = stream.read(self.config.chunk_size)
                frames.append(data.copy())
                
                if not process_frame(data):
                    break
                
                frame_count += 1
                await asyncio.sleep(0)  # Yield to event loop
        
        if not frames:
            return b""
        
        audio_data = np.concatenate(frames)
        return self._to_wav_bytes(audio_data)
    
    def record_seconds(self, duration: float) -> bytes:
        """Record for a fixed number of seconds"""
        try:
            import sounddevice as sd
            
            num_samples = int(duration * self.config.sample_rate)
            
            audio_data = sd.rec(
                num_samples,
                samplerate=self.config.sample_rate,
                channels=self.config.channels,
                dtype=self.config.format
            )
            sd.wait()
            
            return self._to_wav_bytes(audio_data)
            
        except ImportError:
            raise RuntimeError("sounddevice not installed")


class AudioPlayer:
    """Handles audio playback"""
    
    def __init__(self, sample_rate: int = 16000):
        self.sample_rate = sample_rate
    
    def play_bytes(self, audio_data: bytes, format: str = "wav"):
        """Play audio from bytes"""
        try:
            import sounddevice as sd
            
            if format == "wav":
                # Parse WAV data
                buffer = io.BytesIO(audio_data)
                with wave.open(buffer, "rb") as wav_file:
                    sample_rate = wav_file.getframerate()
                    audio_array = np.frombuffer(
                        wav_file.readframes(wav_file.getnframes()),
                        dtype=np.int16
                    )
            elif format == "mp3":
                # Need pydub for MP3
                try:
                    from pydub import AudioSegment
                    audio = AudioSegment.from_mp3(io.BytesIO(audio_data))
                    audio_array = np.array(audio.get_array_of_samples())
                    sample_rate = audio.frame_rate
                except ImportError:
                    raise RuntimeError("pydub required for MP3 playback")
            else:
                raise ValueError(f"Unsupported format: {format}")
            
            sd.play(audio_array, samplerate=sample_rate)
            sd.wait()
            
        except ImportError:
            raise RuntimeError("sounddevice not installed")
    
    async def play_bytes_async(self, audio_data: bytes, format: str = "wav"):
        """Play audio asynchronously"""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.play_bytes, audio_data, format)
    
    def play_file(self, file_path: str):
        """Play audio from file"""
        with open(file_path, "rb") as f:
            audio_data = f.read()
        
        format = Path(file_path).suffix.lstrip(".")
        self.play_bytes(audio_data, format)
    
    def stop(self):
        """Stop any playing audio"""
        try:
            import sounddevice as sd
            sd.stop()
        except:
            pass


class StreamingAudioProcessor:
    """
    Handles streaming audio processing for real-time transcription
    """
    
    def __init__(self, config: Optional[AudioConfig] = None):
        self.config = config or AudioConfig()
        self._buffer = queue.Queue()
        self._is_streaming = False
    
    def start_stream(self) -> Generator[bytes, None, None]:
        """Start streaming audio and yield chunks"""
        try:
            import sounddevice as sd
            
            self._is_streaming = True
            
            def callback(indata, frames, time, status):
                if self._is_streaming:
                    self._buffer.put(indata.copy())
            
            with sd.InputStream(
                samplerate=self.config.sample_rate,
                channels=self.config.channels,
                dtype=self.config.format,
                blocksize=self.config.chunk_size,
                callback=callback
            ):
                while self._is_streaming:
                    try:
                        chunk = self._buffer.get(timeout=0.1)
                        yield chunk.tobytes()
                    except queue.Empty:
                        continue
                        
        except ImportError:
            raise RuntimeError("sounddevice not installed")
    
    def stop_stream(self):
        """Stop the audio stream"""
        self._is_streaming = False
