from pydantic_settings import BaseSettings
from typing import Optional
from enum import Enum

class LLMProvider(str, Enum):
    GROQ = "groq"
    CEREBRAS = "cerebras"
    OLLAMA = "ollama"
    # Future: OPENAI = "openai", ANTHROPIC = "anthropic"

class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql://voicevault_user:your_password_here@localhost:5432/voicevault"
    
    # LLM Configuration
    llm_provider: LLMProvider = LLMProvider.GROQ
    llm_model: str = "llama-3.3-70b-versatile"  # Groq default
    
    # API Keys
    groq_api_key: Optional[str] = None
    cerebras_api_key: Optional[str] = None
    huggingface_token: Optional[str] = None

    # Ollama Configuration
    ollama_base_url: str = "http://localhost:11434"  # Default Ollama URL
    ollama_model: str = "llama3.2"  # Default Ollama model
    
    # Authentication
    access_token: Optional[str] = None  # Global access token for PoC
    
    # File Storage
    upload_dir: str = "uploads"
    max_upload_size: int = 500 * 1024 * 1024  # 500MB (chunking allows large files)
    max_file_size: int = 26214400  # This gets overridden by MAX_FILE_SIZE env var (25MB chunk limit)
    
    # S3 Configuration
    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket_name: str = "voicevault"
    
    # Supported file types (with audio conversion to MP3 for Groq compatibility)
    # FFmpeg can convert most audio/video formats to MP3 for Groq processing
    supported_audio_formats: list[str] = [
        "mp3", "wav", "m4a", "flac", "aac", "ogg", "wma"
    ]
    supported_video_formats: list[str] = [
        "mp4", "avi", "mov", "mkv", "webm", "mpeg", "mpg"
    ]
    
    # Processing
    processing_timeout: int = 3600  # 1 hour
    
    # Development
    debug: bool = False
    log_level: str = "info"
    
    class Config:
        env_file = ".env"

settings = Settings()
