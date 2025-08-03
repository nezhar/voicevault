import os
import asyncio
import tempfile
import subprocess
from typing import List, Tuple, Optional
from loguru import logger

from app.core.config import settings


class AudioChunkingService:
    """Service for splitting large audio files into smaller chunks for Groq processing"""
    
    def __init__(self):
        self.chunk_duration = settings.audio_chunk_duration  # seconds
        self.max_chunk_size = settings.max_file_size  # bytes from environment MAX_FILE_SIZE
    
    async def chunk_audio_file(self, input_file_path: str, entry_id: str) -> Tuple[bool, List[str], Optional[str]]:
        """
        Split an audio file into smaller chunks that meet Groq's size requirements.
        
        Args:
            input_file_path: Path to the input audio file
            entry_id: Entry ID for logging purposes
            
        Returns:
            Tuple[success, list_of_chunk_paths, error_message]
        """
        try:
            # First, check if the file actually needs chunking
            file_size = os.path.getsize(input_file_path)
            if file_size <= self.max_chunk_size:
                logger.info(f"Entry {entry_id}: File size {file_size} bytes is within Groq limits, no chunking needed")
                return True, [input_file_path], None
            
            logger.info(f"Entry {entry_id}: File size {file_size} bytes exceeds Groq limit {self.max_chunk_size}, chunking required")
            
            # Get audio duration to calculate optimal chunk size
            duration = await self._get_audio_duration(input_file_path)
            if not duration:
                return False, [], "Could not determine audio duration"
            
            logger.info(f"Entry {entry_id}: Audio duration: {duration:.2f} seconds")
            
            # Use a conservative approach: calculate chunk duration to ensure size limits
            # Target size should be well under the limit to account for compression variations
            target_chunk_size = self.max_chunk_size * 0.8  # Use 80% of limit as safety margin
            
            # Estimate bitrate from file size and duration
            estimated_bitrate = (file_size * 8) / duration  # bits per second
            
            # Calculate target duration based on estimated bitrate and target size
            target_duration = (target_chunk_size * 8) / estimated_bitrate
            
            # Use the smaller of our configured duration or calculated duration
            chunk_duration = min(self.chunk_duration, target_duration)
            
            # Ensure reasonable bounds
            chunk_duration = max(chunk_duration, 30)   # At least 30 seconds
            chunk_duration = min(chunk_duration, 600)  # At most 10 minutes
            
            num_chunks_estimate = int(duration / chunk_duration) + 1
            logger.info(f"Entry {entry_id}: Will create approximately {num_chunks_estimate} chunks of {chunk_duration:.1f} seconds each")
            
            # Create chunks
            chunk_paths = await self._create_chunks(input_file_path, chunk_duration, entry_id)
            
            if not chunk_paths:
                return False, [], "Failed to create audio chunks"
            
            # Verify all chunks are within size limits
            oversized_chunks = []
            for chunk_path in chunk_paths:
                chunk_size = os.path.getsize(chunk_path)
                if chunk_size > self.max_chunk_size:
                    oversized_chunks.append((chunk_path, chunk_size))
            
            if oversized_chunks:
                # Clean up chunks
                for chunk_path in chunk_paths:
                    try:
                        os.unlink(chunk_path)
                    except:
                        pass
                
                error_msg = f"Some chunks still exceed size limit: {oversized_chunks}"
                logger.error(f"Entry {entry_id}: {error_msg}")
                return False, [], error_msg
            
            logger.info(f"Entry {entry_id}: Successfully created {len(chunk_paths)} chunks")
            return True, chunk_paths, None
            
        except Exception as e:
            error_msg = f"Error chunking audio file: {str(e)}"
            logger.error(f"Entry {entry_id}: {error_msg}")
            return False, [], error_msg
    
    async def _get_audio_duration(self, file_path: str) -> Optional[float]:
        """Get audio duration in seconds using ffprobe"""
        try:
            cmd = [
                'ffprobe',
                '-v', 'quiet',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                file_path
            ]
            
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            )
            
            if result.returncode == 0 and result.stdout.strip():
                return float(result.stdout.strip())
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting audio duration: {str(e)}")
            return None
    
    async def _create_chunks(self, input_file_path: str, chunk_duration: float, entry_id: str) -> List[str]:
        """Create audio chunks using ffmpeg"""
        chunk_paths = []
        
        try:
            # Create temporary directory for chunks
            temp_dir = tempfile.mkdtemp(prefix=f"chunks_{entry_id}_")
            
            # Get the file extension
            _, ext = os.path.splitext(input_file_path)
            if not ext:
                ext = '.mp3'  # Default to mp3
            
            # Use ffmpeg to split the audio
            chunk_pattern = os.path.join(temp_dir, f"chunk_%03d{ext}")
            
            cmd = [
                'ffmpeg',
                '-i', input_file_path,
                '-f', 'segment',
                '-segment_time', str(chunk_duration),
                '-c:a', 'libmp3lame',  # Re-encode to MP3 to ensure compatibility and size control
                '-b:a', '128k',        # 128kbps bitrate to control file size
                '-ar', '44100',        # Standard sample rate
                '-ac', '2',            # Stereo
                '-avoid_negative_ts', 'make_zero',
                '-reset_timestamps', '1',  # Reset timestamps for each segment
                '-y',  # Overwrite output files
                chunk_pattern
            ]
            
            logger.info(f"Entry {entry_id}: Running ffmpeg command: {' '.join(cmd)}")
            
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: subprocess.run(cmd, capture_output=True, text=True, timeout=600)  # 10 minute timeout
            )
            
            if result.returncode != 0:
                logger.error(f"Entry {entry_id}: ffmpeg chunking failed: {result.stderr}")
                return []
            
            # Collect created chunk files
            for i in range(1000):  # Safety limit
                chunk_file = os.path.join(temp_dir, f"chunk_{i:03d}{ext}")
                if os.path.exists(chunk_file):
                    chunk_paths.append(chunk_file)
                else:
                    break
            
            logger.info(f"Entry {entry_id}: Created {len(chunk_paths)} chunks in {temp_dir}")
            return chunk_paths
            
        except Exception as e:
            logger.error(f"Entry {entry_id}: Error creating chunks: {str(e)}")
            # Clean up any partial chunks
            for chunk_path in chunk_paths:
                try:
                    os.unlink(chunk_path)
                except:
                    pass
            return []
    
    def cleanup_chunks(self, chunk_paths: List[str]):
        """Clean up temporary chunk files"""
        for chunk_path in chunk_paths:
            try:
                os.unlink(chunk_path)
                logger.debug(f"Cleaned up chunk: {chunk_path}")
            except Exception as e:
                logger.warning(f"Failed to clean up chunk {chunk_path}: {str(e)}")
        
        # Also try to clean up the parent directory if it's empty
        if chunk_paths:
            try:
                parent_dir = os.path.dirname(chunk_paths[0])
                os.rmdir(parent_dir)
                logger.debug(f"Cleaned up chunk directory: {parent_dir}")
            except:
                pass  # Directory might not be empty or might not exist
    
    async def health_check(self) -> bool:
        """Check if ffmpeg is available for chunking"""
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(['ffmpeg', '-version'], 
                                     capture_output=True, text=True, timeout=10)
            )
            return result.returncode == 0
        except Exception:
            return False