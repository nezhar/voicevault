import asyncio
from typing import List
from loguru import logger

from app.models.entry import Entry, EntryStatus, SourceType
from app.services.database import get_async_db, AsyncSessionLocal
from app.services.entry_service import EntryService
from app.services.download_service import DownloadService
from app.services.asr_service import ASRService
from app.core.config import settings, WorkerMode

class WorkerService:
    def __init__(self):
        self.download_service = DownloadService()
        self.asr_service = ASRService() if settings.worker_mode == WorkerMode.ASR else None
        self.is_running = False
        self.mode = settings.worker_mode
    
    async def start(self):
        """Start the worker processing loop"""
        
        self.is_running = True
        logger.info(f"Worker service started in {self.mode.value.upper()} mode")
        
        while self.is_running:
            try:
                if self.mode == WorkerMode.DOWNLOAD:
                    await self.process_download_entries()
                elif self.mode == WorkerMode.ASR:
                    await self.process_asr_entries()
                
                await asyncio.sleep(settings.worker_interval)
                
            except KeyboardInterrupt:
                logger.info("Received shutdown signal")
                break
            except Exception as e:
                logger.error(f"Error in worker loop: {str(e)}")
                await asyncio.sleep(settings.worker_interval)
        
        logger.info("Worker service stopped")
    
    def stop(self):
        """Stop the worker processing loop"""
        self.is_running = False
    
    async def process_download_entries(self):
        """Process entries for download (DOWNLOAD worker mode)"""
        
        async with AsyncSessionLocal() as db:
            entry_service = EntryService(db)
            
            # Process URL entries that need downloading
            url_entries = await entry_service.fetch_new_entries_for_download()
            
            # Move upload entries to IN_PROGRESS
            await entry_service.fetch_new_uploads_for_processing()
            
            if not url_entries:
                logger.debug("No URL entries to download")
                return
            
            logger.info(f"Processing {len(url_entries)} URL entries for download")
            
            # Process each entry
            for entry in url_entries:
                await self.process_download_entry(entry, entry_service)
    
    async def process_asr_entries(self):
        """Process entries for ASR (ASR worker mode)"""
        
        async with AsyncSessionLocal() as db:
            entry_service = EntryService(db)
            
            # Fetch IN_PROGRESS entries for ASR
            in_progress_entries = await entry_service.fetch_in_progress_entries()
            
            if not in_progress_entries:
                logger.debug("No IN_PROGRESS entries for ASR")
                return
            
            logger.info(f"Processing {len(in_progress_entries)} entries for ASR")
            
            # Process each entry
            for entry in in_progress_entries:
                await self.process_asr_entry(entry, entry_service)
    
    async def process_download_entry(self, entry: Entry, entry_service: EntryService):
        """Process a single entry for download"""
        
        logger.info(f"Downloading entry {entry.id}: {entry.title}")
        
        try:
            # Mark entry as in progress
            await entry_service.update_entry_status(entry.id, EntryStatus.IN_PROGRESS)
            
            # Download from URL
            success = await self.process_url_download(entry, entry_service)
            
            if success:
                logger.info(f"Successfully downloaded entry {entry.id}")
            else:
                logger.warning(f"Failed to download entry {entry.id} from URL: {entry.source_url}")
            
        except Exception as e:
            error_msg = f"Error downloading entry {entry.id}: {str(e)}"
            logger.error(error_msg)
            
            # Mark entry as NEW with error message for retry
            await entry_service.update_entry_status(
                entry.id,
                EntryStatus.NEW,
                error_message=error_msg
            )
    
    async def process_asr_entry(self, entry: Entry, entry_service: EntryService):
        """Process a single entry for ASR"""
        
        logger.info(f"Transcribing entry {entry.id}: {entry.title}")
        
        try:
            if not entry.file_path:
                error_msg = "No file path available for transcription"
                await entry_service.update_entry_status(
                    entry.id,
                    EntryStatus.ERROR,
                    error_message=error_msg
                )
                return
            
            # Validate file before transcription (file_path now contains S3 key)
            try:
                is_valid, validation_error = self.asr_service.validate_audio_file(entry.file_path)
                if not is_valid:
                    # Check if this is a size-related error that chunking can handle
                    size_related_keywords = [
                        "too large", "file size", "groq processing", "max:", "bytes", 
                        "exceeds", "file too large for groq", "26214400", "34046591", "47700599",
                        "file too large for groq processing", "(max:", "file too large for upload",
                        "file too large for conversion", "size exceeds", "file size exceeds",
                        "file size limit", "size limit", "large file", "chunk"
                    ]
                    is_size_error = validation_error and any(keyword in validation_error.lower() for keyword in size_related_keywords)
                    
                    if is_size_error:
                        logger.info(f"Entry {entry.id}: Large file detected, will use chunking for processing: {validation_error}")
                        # Update status to show that chunking will be used for large file
                        await entry_service.update_entry_status(
                            entry.id,
                            EntryStatus.IN_PROGRESS,
                            error_message="Processing large file in chunks for optimal performance"
                        )
                        # Continue to transcription where chunking will handle size issues
                    else:
                        # Non-size related file validation errors are usually permanent
                        await entry_service.update_entry_status(
                            entry.id,
                            EntryStatus.ERROR,
                            error_message=f"File validation failed: {validation_error}"
                        )
                        return
            except Exception as e:
                logger.error(f"Error validating file for entry {entry.id}: {str(e)}")
                await entry_service.update_entry_status(
                    entry.id,
                    EntryStatus.ERROR,
                    error_message=f"File validation error: {str(e)}"
                )
                return
            
            # Perform transcription (file_path contains S3 key)
            logger.info(f"Entry {entry.id}: Starting transcription process")
            success, transcript, error_msg = await self.asr_service.transcribe_file(
                entry.file_path,
                str(entry.id)
            )
            
            # Debug logging to see what's returned
            logger.info(f"Entry {entry.id}: Transcription result - success: {success}, transcript_length: {len(transcript) if transcript else 0}, error: {error_msg}")
            
            if success and transcript:
                # Save transcript and mark as READY
                logger.info(f"Entry {entry.id}: Transcription successful, saving transcript ({len(transcript)} characters)")
                await entry_service.update_entry_transcript(entry.id, transcript)
                logger.info(f"Successfully transcribed entry {entry.id}")
            else:
                # Debug why transcription failed
                if not success:
                    logger.warning(f"Entry {entry.id}: Transcription marked as unsuccessful")
                if not transcript:
                    logger.warning(f"Entry {entry.id}: No transcript returned")
                if error_msg:
                    logger.warning(f"Entry {entry.id}: Error message: {error_msg}")
                
                # Check if error is permanent
                if error_msg and self.asr_service.is_permanent_error(error_msg):
                    # Permanent error - mark as ERROR status
                    await entry_service.update_entry_status(
                        entry.id,
                        EntryStatus.ERROR,
                        error_message=error_msg or "Transcription failed (permanent error)"
                    )
                    logger.error(f"Entry {entry.id} permanent transcription error: {error_msg}")
                else:
                    # Temporary error - mark as NEW for retry
                    await entry_service.update_entry_status(
                        entry.id,
                        EntryStatus.NEW,
                        error_message=error_msg or "Transcription failed (will retry)"
                    )
                    logger.warning(f"Entry {entry.id} temporary transcription error: {error_msg}")
            
        except Exception as e:
            error_msg = f"Error transcribing entry {entry.id}: {str(e)}"
            logger.error(error_msg)
            
            # For unexpected exceptions, determine if permanent
            if self.asr_service.is_permanent_error(str(e)):
                await entry_service.update_entry_status(
                    entry.id,
                    EntryStatus.ERROR,
                    error_message=error_msg
                )
            else:
                # Mark entry as NEW with error message for retry
                await entry_service.update_entry_status(
                    entry.id,
                    EntryStatus.NEW,
                    error_message=error_msg
                )
    
    async def process_url_download(self, entry: Entry, entry_service: EntryService) -> bool:
        """Process URL entry by downloading the content"""
        
        if not entry.source_url:
            await entry_service.update_entry_status(
                entry.id,
                EntryStatus.NEW,
                error_message="Missing source URL"
            )
            return False
        
        logger.info(f"Downloading from URL: {entry.source_url}")
        
        # Download the file
        success, result, error_msg = await self.download_service.download_from_url(
            entry.source_url,
            str(entry.id)
        )
        
        if success and result:
            # result is now (s3_key, filename) tuple
            s3_key, filename = result
            
            # Update entry with S3 key as file path and filename
            await entry_service.update_entry_file_path(entry.id, s3_key, filename)
            
            # Mark as IN_PROGRESS for ASR processing (not READY)
            await entry_service.update_entry_status(
                entry.id,
                EntryStatus.IN_PROGRESS
            )
            
            logger.info(f"Entry {entry.id} download completed and uploaded to S3: {s3_key}")
            return True
            
        else:
            # Check if error is permanent
            if error_msg and self.download_service.is_permanent_error(error_msg):
                # Check if it's a YouTube authentication error specifically
                if self.download_service.is_youtube_auth_error(error_msg):
                    # YouTube auth error - provide helpful message but mark as ERROR
                    friendly_msg = "YouTube requires authentication. This video may be age-restricted or require sign-in. Please try a different video or contact administrator to configure authentication."
                    await entry_service.update_entry_status(
                        entry.id,
                        EntryStatus.ERROR,
                        error_message=friendly_msg
                    )
                    logger.warning(f"Entry {entry.id} YouTube authentication required: {error_msg}")
                else:
                    # Other permanent error
                    await entry_service.update_entry_status(
                        entry.id,
                        EntryStatus.ERROR,
                        error_message=error_msg or "Download failed (permanent error)"
                    )
                    logger.error(f"Entry {entry.id} permanent download error: {error_msg}")
            else:
                # Temporary error - mark as NEW for retry
                await entry_service.update_entry_status(
                    entry.id,
                    EntryStatus.NEW,
                    error_message=error_msg or "Download failed (will retry)"
                )
                logger.warning(f"Entry {entry.id} temporary download error: {error_msg}")
            
            # Clean up any partial downloads (local files only, S3 cleanup handled in download service)
            self.download_service.cleanup_failed_download(str(entry.id))
            
            return False