"""
Voice Agent Configuration Settings
"""
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional
from enum import Enum


class SupportedLanguage(str, Enum):
    TAMIL = "tamil"
    ENGLISH = "english"


# Language to ISO code mapping
LANGUAGE_CODES = {
    "tamil": "ta-IN",
    "english": "en-IN",
}

# Whisper language codes
WHISPER_LANGUAGE_CODES = {
    "tamil": "ta",
    "english": "en",
}

# Azure TTS Voice Names for Indian Languages
AZURE_VOICE_NAMES = {
    "tamil": "ta-IN-PallaviNeural",
    "english": "en-IN-NeerjaNeural",
}


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # LLM Settings
    openai_api_key: Optional[str] = Field(default=None, alias="OPENAI_API_KEY")
    anthropic_api_key: Optional[str] = Field(default=None, alias="ANTHROPIC_API_KEY")
    llm_model: str = Field(default="gpt-4o", alias="LLM_MODEL")
    
    # Azure Speech Services
    azure_speech_key: Optional[str] = Field(default=None, alias="AZURE_SPEECH_KEY")
    azure_speech_region: str = Field(default="centralindia", alias="AZURE_SPEECH_REGION")
    
    # Language Settings
    default_language: SupportedLanguage = Field(
        default=SupportedLanguage.TAMIL, 
        alias="DEFAULT_LANGUAGE"
    )
    fallback_language: SupportedLanguage = Field(
        default=SupportedLanguage.ENGLISH,
        alias="FALLBACK_LANGUAGE"
    )
    
    # Ollama Settings (Free Local LLM)
    ollama_base_url: str = Field(default="http://localhost:11434", alias="OLLAMA_BASE_URL")
    ollama_model: str = Field(default="llama3.2", alias="OLLAMA_MODEL")
    
    # Agent Configuration
    max_planning_iterations: int = Field(default=5, alias="MAX_PLANNING_ITERATIONS")
    memory_window_size: int = Field(default=20, alias="MEMORY_WINDOW_SIZE")
    confidence_threshold: float = Field(default=0.7, alias="CONFIDENCE_THRESHOLD")
    
    # Audio Settings
    sample_rate: int = Field(default=16000, alias="SAMPLE_RATE")
    audio_channels: int = Field(default=1, alias="AUDIO_CHANNELS")
    
    # Server Settings
    host: str = Field(default="0.0.0.0", alias="HOST")
    port: int = Field(default=8000, alias="PORT")
    debug: bool = Field(default=True, alias="DEBUG")
    
    # Vector Store
    chroma_persist_dir: str = Field(default="./data/chroma_db", alias="CHROMA_PERSIST_DIR")
    embedding_model: str = Field(
        default="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        alias="EMBEDDING_MODEL"
    )
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

    def get_language_code(self, language: Optional[str] = None) -> str:
        """Get ISO language code for the specified or default language"""
        lang = language or self.default_language.value
        return LANGUAGE_CODES.get(lang, "en-IN")
    
    def get_whisper_code(self, language: Optional[str] = None) -> str:
        """Get Whisper language code"""
        lang = language or self.default_language.value
        return WHISPER_LANGUAGE_CODES.get(lang, "en")
    
    def get_azure_voice(self, language: Optional[str] = None) -> str:
        """Get Azure TTS voice name"""
        lang = language or self.default_language.value
        return AZURE_VOICE_NAMES.get(lang, "en-IN-NeerjaNeural")


# Global settings instance
settings = Settings()
