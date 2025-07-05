import asyncio
from typing import List
from loguru import logger

from app.models.entry import Entry, EntryStatus, SourceType
from app.services.database import get_async_db
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
        
        async for db in get_async_db():
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
        
        async for db in get_async_db():
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
                logger.warning(f"Failed to download entry {entry.id}")
            
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
            is_valid, validation_error = self.asr_service.validate_audio_file(entry.file_path)
            if not is_valid:
                # File validation errors are usually permanent
                await entry_service.update_entry_status(
                    entry.id,
                    EntryStatus.ERROR,
                    error_message=f"File validation failed: {validation_error}"
                )
                return
            
            # Perform transcription (file_path contains S3 key)
            success, transcript, error_msg = await self.asr_service.transcribe_file(
                entry.file_path,
                str(entry.id)
            )
            
            if success and transcript:
                # Save transcript and mark as READY
                await entry_service.update_entry_transcript(entry.id, transcript)
                logger.info(f"Successfully transcribed entry {entry.id}")
            else:
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
                # Permanent error - mark as ERROR status
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