from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from typing import List, Optional
from uuid import UUID
import asyncio
from loguru import logger

from app.models.entry import Entry, EntryStatus, SourceType
from app.core.config import settings

class EntryService:
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def fetch_new_entries_for_download(self, limit: int = None) -> List[Entry]:
        """Fetch NEW entries with URLs for download processing"""
        
        if limit is None:
            limit = settings.batch_size
        
        query = (
            select(Entry)
            .where(
                Entry.status == EntryStatus.NEW,
                Entry.source_type == SourceType.URL,
                Entry.source_url.isnot(None)
            )
            .order_by(Entry.created_at)
            .limit(limit)
        )
        
        result = await self.db.execute(query)
        entries = result.scalars().all()
        
        logger.info(f"Fetched {len(entries)} NEW URL entries for download")
        return list(entries)
    
    async def fetch_new_uploads_for_processing(self, limit: int = None) -> List[Entry]:
        """Fetch NEW upload entries and move them to IN_PROGRESS"""
        
        if limit is None:
            limit = settings.batch_size
        
        query = (
            select(Entry)
            .where(
                Entry.status == EntryStatus.NEW,
                Entry.source_type == SourceType.UPLOAD,
                Entry.file_path.isnot(None)
            )
            .order_by(Entry.created_at)
            .limit(limit)
        )
        
        result = await self.db.execute(query)
        entries = result.scalars().all()
        
        # Move upload entries directly to IN_PROGRESS
        for entry in entries:
            await self.update_entry_status(entry.id, EntryStatus.IN_PROGRESS)
        
        logger.info(f"Moved {len(entries)} NEW upload entries to IN_PROGRESS")
        return list(entries)
    
    async def fetch_in_progress_entries(self, limit: int = None) -> List[Entry]:
        """Fetch IN_PROGRESS entries for ASR processing"""
        
        if limit is None:
            limit = settings.batch_size
        
        query = (
            select(Entry)
            .where(
                Entry.status == EntryStatus.IN_PROGRESS,
                Entry.file_path.isnot(None)
            )
            .order_by(Entry.created_at)
            .limit(limit)
        )
        
        result = await self.db.execute(query)
        entries = result.scalars().all()
        
        logger.info(f"Fetched {len(entries)} IN_PROGRESS entries for ASR")
        return list(entries)
    
    async def update_entry_status(
        self, 
        entry_id: UUID, 
        status: EntryStatus,
        error_message: Optional[str] = None
    ) -> bool:
        """Update entry status and optional error message"""
        
        try:
            update_data = {"status": status}
            if error_message:
                update_data["error_message"] = error_message
            else:
                # Clear error message when status changes successfully
                update_data["error_message"] = None
            
            query = (
                update(Entry)
                .where(Entry.id == entry_id)
                .values(**update_data)
            )
            
            await self.db.execute(query)
            await self.db.commit()
            
            logger.info(f"Updated entry {entry_id} status to {status}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update entry {entry_id}: {str(e)}")
            await self.db.rollback()
            return False
    
    async def update_entry_file_path(self, entry_id: UUID, file_path: str, filename: Optional[str] = None) -> bool:
        """Update entry with downloaded file path"""
        
        try:
            update_data = {"file_path": file_path}
            if filename:
                update_data["filename"] = filename
            
            query = (
                update(Entry)
                .where(Entry.id == entry_id)
                .values(**update_data)
            )
            
            await self.db.execute(query)
            await self.db.commit()
            
            logger.info(f"Updated entry {entry_id} file path: {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update file path for entry {entry_id}: {str(e)}")
            await self.db.rollback()
            return False
    
    async def get_entry_by_id(self, entry_id: UUID) -> Optional[Entry]:
        """Get entry by ID"""
        
        query = select(Entry).where(Entry.id == entry_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()
    
    async def update_entry_transcript(self, entry_id: UUID, transcript: str) -> bool:
        """Update entry transcript and mark as READY"""
        
        try:
            query = (
                update(Entry)
                .where(Entry.id == entry_id)
                .values(
                    transcript=transcript,
                    status=EntryStatus.READY,
                    error_message=None  # Clear any previous errors
                )
            )
            
            await self.db.execute(query)
            await self.db.commit()
            
            logger.info(f"Updated entry {entry_id} transcript and marked as READY ({len(transcript)} chars)")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update transcript for entry {entry_id}: {str(e)}")
            await self.db.rollback()
            return False