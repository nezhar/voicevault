import os
import asyncio
import subprocess
import tempfile
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
        self._s3_service = None
    
    @property
    def s3_service(self):
        """Lazy initialization of S3 service to avoid async context issues"""
        if self._s3_service is None:
            self._s3_service = S3Service()
        return self._s3_service
    
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
            # Groq free tier limit is 25MB, dev tier is 100MB
            groq_max_size = 25 * 1024 * 1024  # 25MB for free tier
            if file_size > groq_max_size:
                error_msg = f"File too large for Groq transcription: {file_size} bytes (max: {groq_max_size})"
                logger.error(f"Entry {entry_id}: {error_msg}")
                return False, None, error_msg
            
            logger.info(f"Entry {entry_id}: Starting transcription with Groq (S3 key: {s3_key})")
            
            # Run transcription in executor to avoid blocking
            loop = asyncio.get_event_loop()
            transcript = await loop.run_in_executor(
                None,
                self._transcribe_sync,
                temp_file_path,
                s3_key
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
    
    def _transcribe_sync(self, file_path: str, s3_key: str = None) -> Optional[str]:
        """Synchronous transcription function to run in executor"""
        
        extracted_audio_path = None
        try:
            # Check if we need to extract audio from video using the original S3 key
            original_filename = s3_key if s3_key else file_path
            if self._is_video_file(original_filename):
                logger.info(f"Video file detected, extracting audio: {original_filename}")
                extracted_audio_path = self._extract_audio_from_video(file_path)
                if not extracted_audio_path:
                    raise Exception("Failed to extract audio from video file")
                transcription_file = extracted_audio_path
            else:
                transcription_file = file_path
            
            with open(transcription_file, "rb") as audio_file:
                # Call Groq API for transcription with updated client structure
                transcription = self.client.audio.transcriptions.create(
                    file=audio_file,
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
        finally:
            # Clean up extracted audio file if it was created
            if extracted_audio_path and os.path.exists(extracted_audio_path):
                try:
                    os.unlink(extracted_audio_path)
                    logger.debug(f"Cleaned up extracted audio file: {extracted_audio_path}")
                except Exception as e:
                    logger.warning(f"Failed to clean up extracted audio file: {str(e)}")
    
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
            
            # Check file extension from S3 key (Groq supported formats)
            path = Path(s3_key)
            # Groq supported formats: flac, mp3, mp4, mpeg, mpga, m4a, ogg, wav, webm
            supported_extensions = ['.flac', '.mp3', '.mp4', '.mpeg', '.mpga', '.m4a', '.ogg', '.wav', '.webm']
            if path.suffix.lower() not in supported_extensions:
                return False, f"Unsupported file format for Groq: {path.suffix}. Supported: {', '.join(supported_extensions)}"
            
            # Check file size
            file_size = file_info.get('size', 0)
            if file_size == 0:
                return False, "File is empty"
            
            # Groq file size limits
            groq_max_size = 25 * 1024 * 1024  # 25MB for free tier
            if file_size > groq_max_size:
                return False, f"File too large for Groq: {file_size} bytes (max: {groq_max_size})"
            
            return True, None
            
        except Exception as e:
            return False, f"File validation error: {str(e)}"
    
    def get_supported_formats(self) -> list[str]:
        """Get list of Groq supported audio/video formats"""
        return ['.flac', '.mp3', '.mp4', '.mpeg', '.mpga', '.m4a', '.ogg', '.wav', '.webm']
    
    def _is_video_file(self, file_path: str) -> bool:
        """Check if file is a video file that needs audio extraction"""
        video_extensions = ['.mp4', '.webm', '.mpeg']
        path = Path(file_path)
        return path.suffix.lower() in video_extensions
    
    def _extract_audio_from_video(self, video_path: str) -> Optional[str]:
        """Extract audio from video file using FFmpeg"""
        try:
            # Create temporary file for extracted audio
            temp_audio_fd, temp_audio_path = tempfile.mkstemp(suffix='.mp3')
            os.close(temp_audio_fd)
            
            # FFmpeg command to extract audio
            cmd = [
                'ffmpeg',
                '-i', video_path,
                '-vn',  # No video
                '-acodec', 'mp3',  # Audio codec
                '-ab', '128k',  # Audio bitrate
                '-ar', '44100',  # Sample rate
                '-y',  # Overwrite output file
                temp_audio_path
            ]
            
            logger.info(f"Extracting audio from video: {video_path}")
            
            # Run FFmpeg
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            if result.returncode == 0:
                # Check if output file exists and has content
                if os.path.exists(temp_audio_path) and os.path.getsize(temp_audio_path) > 0:
                    logger.info(f"Audio extracted successfully: {temp_audio_path}")
                    return temp_audio_path
                else:
                    logger.error("FFmpeg completed but output file is empty")
                    if os.path.exists(temp_audio_path):
                        os.unlink(temp_audio_path)
                    return None
            else:
                logger.error(f"FFmpeg failed with return code {result.returncode}")
                logger.error(f"FFmpeg stderr: {result.stderr}")
                if os.path.exists(temp_audio_path):
                    os.unlink(temp_audio_path)
                return None
                
        except subprocess.TimeoutExpired:
            logger.error("FFmpeg timed out during audio extraction")
            if os.path.exists(temp_audio_path):
                os.unlink(temp_audio_path)
            return None
        except Exception as e:
            logger.error(f"Error extracting audio: {str(e)}")
            if 'temp_audio_path' in locals() and os.path.exists(temp_audio_path):
                os.unlink(temp_audio_path)
            return None
    
    def is_permanent_error(self, error_message: str) -> bool:
        """Determine if an ASR error is permanent and should not be retried"""
        
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
            "unsupported media type"
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