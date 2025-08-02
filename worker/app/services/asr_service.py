import os
import asyncio
from typing import Optional, Tuple
from groq import Groq
from loguru import logger

from app.core.config import settings
from app.services.s3_service import S3Service
from app.services.audio_conversion_service import AudioConversionService

class ASRService:
    def __init__(self):
        if not settings.groq_api_key:
            raise ValueError("GROQ_API_KEY is required for ASR service")
        
        self.client = Groq(api_key=settings.groq_api_key)
        self.model = settings.groq_model
        self._s3_service = None
        self._audio_conversion_service = None
    
    @property
    def s3_service(self):
        """Lazy initialization of S3 service to avoid async context issues"""
        if self._s3_service is None:
            self._s3_service = S3Service()
        return self._s3_service
    
    @property
    def audio_conversion_service(self):
        """Lazy initialization of audio conversion service"""
        if self._audio_conversion_service is None:
            self._audio_conversion_service = AudioConversionService()
        return self._audio_conversion_service
    
    async def transcribe_file(self, s3_key: str, entry_id: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Transcribe audio/video file from S3 using Groq API
        Ensures file is converted to MP3 format before processing
        
        Returns:
            Tuple[success, transcript, error_message]
        """
        
        # Check if file exists in S3
        if not self.s3_service.file_exists(s3_key):
            error_msg = f"File not found in S3: {s3_key}"
            logger.error(f"Entry {entry_id}: {error_msg}")
            return False, None, error_msg
        
        # Ensure file is in Groq-compatible format (convert to MP3 if needed)
        logger.info(f"Entry {entry_id}: Ensuring Groq compatibility for: {s3_key}")
        conversion_success, groq_compatible_s3_key, conversion_error = await self.audio_conversion_service.ensure_groq_compatibility(s3_key, entry_id)
        
        if not conversion_success:
            error_msg = f"Failed to convert file to Groq-compatible format: {conversion_error}"
            logger.error(f"Entry {entry_id}: {error_msg}")
            return False, None, error_msg
        
        # Use the converted file for transcription
        transcription_s3_key = groq_compatible_s3_key
        logger.info(f"Entry {entry_id}: Using converted file for transcription: {transcription_s3_key}")
        
        # Verify the file exists and get its info
        if not self.s3_service.file_exists(transcription_s3_key):
            error_msg = f"Converted file not found in S3: {transcription_s3_key}"
            logger.error(f"Entry {entry_id}: {error_msg}")
            return False, None, error_msg
        
        file_info = self.s3_service.get_file_info(transcription_s3_key)
        if file_info:
            logger.info(f"Entry {entry_id}: Converted file info - size: {file_info.get('size', 0)} bytes, content_type: {file_info.get('content_type', 'unknown')}")
        
        # Download file to temporary location
        temp_file_path = self.s3_service.create_temp_download(transcription_s3_key)
        if not temp_file_path:
            error_msg = f"Failed to download file from S3: {transcription_s3_key}"
            logger.error(f"Entry {entry_id}: {error_msg}")
            return False, None, error_msg
        
        try:
            # Get file info
            file_size = os.path.getsize(temp_file_path)
            # Check against configured max file size (25MB for free tier, 100MB for dev tier)
            if file_size > settings.max_file_size:
                error_msg = f"File too large for Groq transcription: {file_size} bytes (max: {settings.max_file_size} bytes)"
                logger.error(f"Entry {entry_id}: {error_msg}")
                return False, None, error_msg
            
            logger.info(f"Entry {entry_id}: Starting transcription with Groq (S3 key: {s3_key})")
            
            # Run transcription in executor to avoid blocking
            loop = asyncio.get_event_loop()
            transcript = await loop.run_in_executor(
                None,
                self._transcribe_sync,
                temp_file_path,
                transcription_s3_key,
                entry_id
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
    
    def _transcribe_sync(self, file_path: str, s3_key: str = None, entry_id: str = None) -> Optional[str]:
        """Synchronous transcription function to run in executor"""
        
        try:
            # File is already in Groq-compatible format (MP3) after conversion
            file_size = os.path.getsize(file_path)
            logger.info(f"Entry {entry_id or 'unknown'}: Sending file to Groq - path: {file_path}, size: {file_size} bytes")
            
            # Check the actual file type using the file command
            try:
                import subprocess
                result = subprocess.run(['file', '-b', '--mime-type', file_path], 
                                      capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    detected_type = result.stdout.strip()
                    logger.info(f"Entry {entry_id or 'unknown'}: Detected file type: {detected_type}")
                else:
                    logger.warning(f"Entry {entry_id or 'unknown'}: Could not detect file type")
            except Exception as e:
                logger.warning(f"Entry {entry_id or 'unknown'}: Error detecting file type: {str(e)}")
            
            with open(file_path, "rb") as audio_file:
                # Create a file-like object with proper filename for Groq
                # Groq needs the filename to detect the format properly
                file_name = f"audio_{entry_id or 'unknown'}.mp3"
                logger.info(f"Entry {entry_id or 'unknown'}: Sending to Groq with filename: {file_name}")
                
                # Call Groq API for transcription with file tuple
                # The file parameter needs to be a tuple: (filename, file_object, content_type)
                transcription = self.client.audio.transcriptions.create(
                    file=(file_name, audio_file, "audio/mpeg"),
                    model=self.model,
                    response_format="text",
                    temperature=0.0
                )
                
                # Handle different response formats
                if hasattr(transcription, 'text'):
                    return transcription.text.strip() if transcription.text else None
                elif isinstance(transcription, str):
                    return transcription.strip()
                else:
                    return str(transcription).strip() if transcription else None
                
        except Exception as e:
            logger.error(f"Groq API error: {str(e)}")
            raise
    
    def validate_audio_file(self, s3_key: str) -> Tuple[bool, Optional[str]]:
        """Validate audio file in S3 for transcription"""
        
        try:
            # Use audio conversion service for validation
            # This will check if the file can be converted to MP3/Groq format
            validation_success, validation_error = self.audio_conversion_service.validate_input_file(s3_key)
            
            if not validation_success:
                return False, validation_error
            
            # Get file info from S3 for size check
            file_info = self.s3_service.get_file_info(s3_key)
            if not file_info:
                return False, "Could not get file info from S3"
            
            # Check file size against Groq limits
            file_size = file_info.get('size', 0)
            
            # Check file size against configured max file size (25MB for free tier, 100MB for dev tier)
            if file_size > settings.max_file_size:
                return False, f"File too large for Groq transcription: {file_size} bytes (max: {settings.max_file_size} bytes)"
            
            return True, None
            
        except Exception as e:
            return False, f"File validation error: {str(e)}"
    
    def get_supported_formats(self) -> list[str]:
        """Get list of supported input formats (can be converted to MP3 for Groq)"""
        return self.audio_conversion_service.get_supported_input_formats()
    
    
    def is_permanent_error(self, error_message: str) -> bool:
        """Determine if an ASR error is permanent and should not be retried"""
        
        # Check if it's a conversion service permanent error
        if self.audio_conversion_service.is_permanent_error(error_message):
            return True
        
        permanent_error_patterns = [
            "File not found",
            "Unsupported file format",
            "File too large",
            "File is empty",
            "File validation failed",
            "Invalid API key",
            "Unauthorized",
            "authentication",
            "invalid_request_error",
            "invalid file format",
            "file size exceeds",
            "unsupported media type",
            "Failed to convert file to Groq-compatible format"
        ]
        
        return any(pattern.lower() in error_message.lower() for pattern in permanent_error_patterns)
    
    async def health_check(self) -> bool:
        """Check if Groq API and audio conversion service are accessible"""
        
        try:
            # Check if Groq client is properly initialized
            groq_healthy = self.client is not None and settings.groq_api_key is not None
            
            # Check if audio conversion service is healthy (FFmpeg available)
            conversion_healthy = await self.audio_conversion_service.health_check()
            
            if not groq_healthy:
                logger.error("Groq API client is not properly initialized")
            
            if not conversion_healthy:
                logger.error("Audio conversion service is not healthy")
            
            return groq_healthy and conversion_healthy
            
        except Exception as e:
            logger.error(f"ASR service health check failed: {str(e)}")
            return False
