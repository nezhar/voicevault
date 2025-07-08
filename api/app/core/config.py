from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql://voicevault_user:your_password_here@localhost:5432/voicevault"
    
    # API Keys
    groq_api_key: Optional[str] = None
    huggingface_token: Optional[str] = None
    
    # Authentication
    access_token: Optional[str] = None  # Global access token for PoC
    
    # File Storage
    upload_dir: str = "uploads"
    max_file_size: int = 500 * 1024 * 1024  # 500MB
    
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