from pydantic_settings import BaseSettings
from typing import Optional
from enum import Enum

class WorkerMode(str, Enum):
    DOWNLOAD = "download"
    ASR = "asr"

class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql://voicevault_user:dev_password_123@localhost:5432/voicevault"
    
    # Worker Configuration
    worker_mode: WorkerMode = WorkerMode.DOWNLOAD
    worker_interval: int = 10  # seconds between processing cycles
    max_retries: int = 3
    batch_size: int = 5  # number of entries to process per cycle
    
    # File Storage
    download_dir: str = "downloads"
    max_file_size: int = 500 * 1024 * 1024  # 500MB
    
    # S3 Configuration
    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket_name: str = "voicevault"
    
    # Supported URL sources
    supported_url_domains: list[str] = [
        "youtube.com",
        "youtu.be",
        "vimeo.com",
        "soundcloud.com"
    ]
    
    # Groq API Configuration
    groq_api_key: Optional[str] = None
    groq_model: str = "whisper-large-v3-turbo"
    
    # Logging
    log_level: str = "INFO"
    
    class Config:
        env_file = ".env"

settings = Settings()