import os
import asyncio
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Tuple
from loguru import logger

from app.core.config import settings
from app.services.s3_service import S3Service


class AudioConversionService:
    def __init__(self):
        self.s3_service = S3Service()
        self.target_format = "mp3"
        self.target_bitrate = "128k"
        self.target_sample_rate = "44100"
    
    async def convert_to_mp3(self, input_s3_key: str, entry_id: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Convert audio/video file to MP3 format and store in S3
        Always converts to ensure proper MP3 format for Groq compatibility
        
        Args:
            input_s3_key: S3 key of the input file
            entry_id: Entry ID for generating output key
            
        Returns:
            Tuple[success, output_s3_key, error_message]
        """
        
        # Check if file exists in S3
        if not self.s3_service.file_exists(input_s3_key):
            error_msg = f"Input file not found in S3: {input_s3_key}"
            logger.error(f"Entry {entry_id}: {error_msg}")
            return False, None, error_msg
        
        # Always convert to ensure proper MP3 format for Groq
        # Even if the file extension is .mp3, it might not be in the correct format
        logger.info(f"Entry {entry_id}: Converting to MP3 format: {input_s3_key}")
        
        # Download input file to temporary location
        temp_input_path = self.s3_service.create_temp_download(input_s3_key)
        if not temp_input_path:
            error_msg = f"Failed to download input file from S3: {input_s3_key}"
            logger.error(f"Entry {entry_id}: {error_msg}")
            return False, None, error_msg
        
        try:
            # Generate output file path
            temp_output_fd, temp_output_path = tempfile.mkstemp(suffix='.mp3')
            os.close(temp_output_fd)
            
            # Run conversion in executor to avoid blocking
            loop = asyncio.get_event_loop()
            conversion_success = await loop.run_in_executor(
                None,
                self._convert_to_mp3_sync,
                temp_input_path,
                temp_output_path,
                entry_id
            )
            
            if not conversion_success:
                error_msg = "Audio conversion to MP3 failed"
                logger.error(f"Entry {entry_id}: {error_msg}")
                return False, None, error_msg
            
            # Generate output S3 key
            output_filename = f"{entry_id}.mp3"
            output_s3_key = self.s3_service.generate_s3_key(entry_id, output_filename)
            
            # Upload converted file to S3
            upload_success = self.s3_service.upload_file_from_path(
                temp_output_path, 
                output_s3_key,
                content_type="audio/mpeg"
            )
            
            if not upload_success:
                error_msg = f"Failed to upload converted MP3 to S3: {output_s3_key}"
                logger.error(f"Entry {entry_id}: {error_msg}")
                return False, None, error_msg
            
            logger.info(f"Entry {entry_id}: Successfully converted to MP3: {input_s3_key} -> {output_s3_key}")
            return True, output_s3_key, None
            
        except Exception as e:
            error_msg = f"Audio conversion error: {str(e)}"
            logger.error(f"Entry {entry_id}: {error_msg}")
            return False, None, error_msg
        finally:
            # Clean up temporary files
            self.s3_service.cleanup_temp_file(temp_input_path)
            if 'temp_output_path' in locals() and os.path.exists(temp_output_path):
                try:
                    os.unlink(temp_output_path)
                except Exception as e:
                    logger.warning(f"Failed to cleanup temp output file: {str(e)}")
    
    def _convert_to_mp3_sync(self, input_path: str, output_path: str, entry_id: str) -> bool:
        """Synchronous MP3 conversion using FFmpeg"""
        
        try:
            # FFmpeg command for MP3 conversion with explicit format
            cmd = [
                'ffmpeg',
                '-i', input_path,
                '-vn',  # No video
                '-acodec', 'libmp3lame',  # Use LAME MP3 encoder
                '-ab', self.target_bitrate,  # Audio bitrate
                '-ar', self.target_sample_rate,  # Sample rate
                '-ac', '2',  # Stereo
                '-f', 'mp3',  # Force MP3 format
                '-y',  # Overwrite output file
                output_path
            ]
            
            logger.info(f"Entry {entry_id}: Converting to MP3: {input_path} -> {output_path}")
            logger.debug(f"Entry {entry_id}: FFmpeg command: {' '.join(cmd)}")
            
            # Run FFmpeg
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600  # 10 minute timeout
            )
            
            if result.returncode == 0:
                # Check if output file exists and has content
                if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                    file_size = os.path.getsize(output_path)
                    
                    # Verify the output is actually a valid MP3 file
                    if self._verify_mp3_file(output_path, entry_id):
                        logger.info(f"Entry {entry_id}: MP3 conversion successful. Output size: {file_size} bytes")
                        return True
                    else:
                        logger.error(f"Entry {entry_id}: MP3 conversion produced invalid file")
                        return False
                else:
                    logger.error(f"Entry {entry_id}: FFmpeg completed but output file is empty")
                    return False
            else:
                logger.error(f"Entry {entry_id}: FFmpeg failed with return code {result.returncode}")
                logger.error(f"Entry {entry_id}: FFmpeg stderr: {result.stderr}")
                logger.error(f"Entry {entry_id}: FFmpeg stdout: {result.stdout}")
                return False
                
        except subprocess.TimeoutExpired:
            logger.error(f"Entry {entry_id}: FFmpeg timed out during MP3 conversion")
            return False
        except Exception as e:
            logger.error(f"Entry {entry_id}: Error during MP3 conversion: {str(e)}")
            return False
    
    def _is_mp3_file(self, s3_key: str) -> bool:
        """Check if file is already in MP3 format"""
        path = Path(s3_key)
        return path.suffix.lower() == '.mp3'
    
    def _verify_mp3_file(self, file_path: str, entry_id: str) -> bool:
        """Verify that the file is a valid MP3 file using FFmpeg"""
        try:
            # Use FFmpeg to probe the file and verify it's a valid MP3
            cmd = [
                'ffprobe',
                '-v', 'quiet',
                '-show_format',
                '-show_streams',
                '-of', 'json',
                file_path
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                # Check if the file has MP3 format info
                output = result.stdout
                if 'mp3' in output.lower() and 'audio' in output.lower():
                    logger.debug(f"Entry {entry_id}: MP3 file verification successful")
                    return True
                else:
                    logger.warning(f"Entry {entry_id}: File does not appear to be valid MP3 format")
                    return False
            else:
                logger.error(f"Entry {entry_id}: FFprobe failed to verify MP3 file: {result.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"Entry {entry_id}: Error verifying MP3 file: {str(e)}")
            return False
    
    def validate_input_file(self, s3_key: str) -> Tuple[bool, Optional[str]]:
        """Validate input file for conversion"""
        
        try:
            # Check if file exists in S3
            if not self.s3_service.file_exists(s3_key):
                return False, "File does not exist in S3"
            
            # Get file info from S3
            file_info = self.s3_service.get_file_info(s3_key)
            if not file_info:
                return False, "Could not get file info from S3"
            
            # Check file extension (supported input formats for FFmpeg)
            path = Path(s3_key)
            supported_extensions = [
                '.mp3', '.wav', '.flac', '.aac', '.ogg', '.wma', '.m4a',
                '.mp4', '.avi', '.mov', '.mkv', '.webm', '.mpeg', '.mpg'
            ]
            
            if path.suffix.lower() not in supported_extensions:
                return False, f"Unsupported input format: {path.suffix}. Supported: {', '.join(supported_extensions)}"
            
            # Check file size
            file_size = file_info.get('size', 0)
            if file_size == 0:
                return False, "File is empty"
            
            # Check reasonable file size limits (1GB max)
            max_size = 1024 * 1024 * 1024  # 1GB
            if file_size > max_size:
                return False, f"File too large for conversion: {file_size} bytes (max: {max_size})"
            
            return True, None
            
        except Exception as e:
            return False, f"File validation error: {str(e)}"
    
    def get_supported_input_formats(self) -> list[str]:
        """Get list of supported input formats for conversion"""
        return [
            '.mp3', '.wav', '.flac', '.aac', '.ogg', '.wma', '.m4a',
            '.mp4', '.avi', '.mov', '.mkv', '.webm', '.mpeg', '.mpg'
        ]
    
    def get_groq_compatible_formats(self) -> list[str]:
        """Get list of Groq-compatible formats"""
        return ['.flac', '.mp3', '.mp4', '.mpeg', '.mpga', '.m4a', '.ogg', '.wav', '.webm']
    
    def is_groq_compatible(self, s3_key: str) -> bool:
        """Check if file format is compatible with Groq"""
        path = Path(s3_key)
        return path.suffix.lower() in self.get_groq_compatible_formats()
    
    async def ensure_groq_compatibility(self, s3_key: str, entry_id: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Ensure file is in Groq-compatible format by converting to MP3
        Always converts to guarantee proper format for Groq processing
        
        Args:
            s3_key: S3 key of the input file
            entry_id: Entry ID for processing
            
        Returns:
            Tuple[success, groq_compatible_s3_key, error_message]
        """
        
        # Always convert to MP3 to ensure Groq compatibility
        # This guarantees the file will be in the exact format Groq expects
        logger.info(f"Entry {entry_id}: Ensuring Groq compatibility by converting to MP3: {s3_key}")
        return await self.convert_to_mp3(s3_key, entry_id)
    
    def is_permanent_error(self, error_message: str) -> bool:
        """Determine if a conversion error is permanent and should not be retried"""
        
        permanent_error_patterns = [
            "File not found",
            "Unsupported input format",
            "File too large",
            "File is empty",
            "File validation failed",
            "Invalid file format",
            "file size exceeds",
            "unsupported media type",
            "corrupted file",
            "invalid audio stream",
            "no audio stream found"
        ]
        
        return any(pattern.lower() in error_message.lower() for pattern in permanent_error_patterns)
    
    async def health_check(self) -> bool:
        """Check if FFmpeg is available for conversion"""
        
        try:
            # Check if FFmpeg is installed
            result = subprocess.run(
                ['ffmpeg', '-version'],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                logger.info("FFmpeg is available for audio conversion")
                return True
            else:
                logger.error("FFmpeg is not available")
                return False
                
        except Exception as e:
            logger.error(f"Audio conversion service health check failed: {str(e)}")
            return False