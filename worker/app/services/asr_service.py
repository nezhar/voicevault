import os
import asyncio
from pathlib import Path
from typing import Optional, Tuple
from groq import Groq
from loguru import logger

from app.core.config import settings
from app.services.s3_service import S3Service

class ASRService:
    def __init__(self):
        if not settings.groq_api_key:
            raise ValueError("GROQ_API_KEY is required for ASR service")
        
        self.client = Groq(api_key=settings.groq_api_key)
        self.model = settings.groq_model
        self.s3_service = S3Service()
    
    async def transcribe_file(self, s3_key: str, entry_id: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Transcribe audio/video file from S3 using Groq API
        
        Returns:
            Tuple[success, transcript, error_message]
        """
        
        # Check if file exists in S3
        if not self.s3_service.file_exists(s3_key):
            error_msg = f"File not found in S3: {s3_key}"
            logger.error(f"Entry {entry_id}: {error_msg}")
            return False, None, error_msg
        
        # Download file to temporary location
        temp_file_path = self.s3_service.create_temp_download(s3_key)
        if not temp_file_path:
            error_msg = f"Failed to download file from S3: {s3_key}"
            logger.error(f"Entry {entry_id}: {error_msg}")
            return False, None, error_msg
        
        try:
            # Get file info
            file_size = os.path.getsize(temp_file_path)
            if file_size > settings.max_file_size:
                error_msg = f"File too large for transcription: {file_size} bytes"
                logger.error(f"Entry {entry_id}: {error_msg}")
                return False, None, error_msg
            
            logger.info(f"Entry {entry_id}: Starting transcription with Groq (S3 key: {s3_key})")
            
            # Run transcription in executor to avoid blocking
            loop = asyncio.get_event_loop()
            transcript = await loop.run_in_executor(
                None,
                self._transcribe_sync,
                temp_file_path
            )
            
            if transcript:
                logger.info(f"Entry {entry_id}: Transcription completed ({len(transcript)} characters)")
                return True, transcript, None
            else:
                error_msg = "Empty transcript returned"
                logger.warning(f"Entry {entry_id}: {error_msg}")
                return False, None, error_msg
                
        except Exception as e:
            error_msg = f"Transcription error: {str(e)}"
            logger.error(f"Entry {entry_id}: {error_msg}")
            return False, None, error_msg
        finally:
            # Clean up temporary file
            self.s3_service.cleanup_temp_file(temp_file_path)
    
    def _transcribe_sync(self, file_path: str) -> Optional[str]:
        """Synchronous transcription function to run in executor"""
        
        try:
            with open(file_path, "rb") as audio_file:
                # Call Groq API for transcription
                transcription = self.client.audio.transcriptions.create(
                    file=audio_file,
                    model=self.model,
                    response_format="text",
                    language="en"  # Can be made configurable
                )
                
                # Groq returns the transcript directly as text
                return transcription.strip() if transcription else None
                
        except Exception as e:
            logger.error(f"Groq API error: {str(e)}")
            raise
    
    def validate_audio_file(self, s3_key: str) -> Tuple[bool, Optional[str]]:
        """Validate audio file in S3 for transcription"""
        
        try:
            # Check if file exists in S3
            if not self.s3_service.file_exists(s3_key):
                return False, "File does not exist in S3"
            
            # Get file info from S3
            file_info = self.s3_service.get_file_info(s3_key)
            if not file_info:
                return False, "Could not get file info from S3"
            
            # Check file extension from S3 key
            path = Path(s3_key)
            supported_extensions = ['.mp3', '.wav', '.m4a', '.flac', '.mp4', '.webm', '.ogg']
            if path.suffix.lower() not in supported_extensions:
                return False, f"Unsupported file format: {path.suffix}"
            
            # Check file size
            file_size = file_info.get('size', 0)
            if file_size == 0:
                return False, "File is empty"
            
            if file_size > settings.max_file_size:
                return False, f"File too large: {file_size} bytes"
            
            return True, None
            
        except Exception as e:
            return False, f"File validation error: {str(e)}"
    
    def get_supported_formats(self) -> list[str]:
        """Get list of supported audio/video formats"""
        return ['.mp3', '.wav', '.m4a', '.flac', '.mp4', '.webm', '.ogg', '.avi', '.mov']
    
    def is_permanent_error(self, error_message: str) -> bool:
        """Determine if an ASR error is permanent and should not be retried"""
        
        permanent_error_patterns = [
            "File not found",
            "Unsupported file format",
            "File too large",
            "File is empty",
            "File validation failed",
            "Invalid API key",
            "Unauthorized"
        ]
        
        return any(pattern.lower() in error_message.lower() for pattern in permanent_error_patterns)
    
    async def health_check(self) -> bool:
        """Check if Groq API is accessible"""
        
        try:
            # Simple test to verify API key works
            # Note: This would require a small test file or different approach
            # For now, just check if client is properly initialized
            return self.client is not None and settings.groq_api_key is not None
            
        except Exception as e:
            logger.error(f"ASR service health check failed: {str(e)}")
            return False