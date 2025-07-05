from sqlalchemy.orm import Session
from typing import Optional, Tuple, List
from uuid import UUID
import os
from pathlib import Path

from app.models.entry import Entry, EntryStatus, SourceType
from app.core.config import settings

class EntryService:
    def __init__(self, db: Session):
        self.db = db
    
    def create_entry(
        self,
        title: str,
        source_type: SourceType,
        source_url: Optional[str] = None,
        filename: Optional[str] = None
    ) -> Entry:
        """Create a new entry"""
        
        entry = Entry(
            title=title,
            source_type=source_type,
            source_url=source_url,
            filename=filename,
            status=EntryStatus.NEW
        )
        
        self.db.add(entry)
        self.db.commit()
        self.db.refresh(entry)
        
        return entry
    
    def get_entry(self, entry_id: UUID) -> Optional[Entry]:
        """Get entry by ID"""
        return self.db.query(Entry).filter(Entry.id == entry_id).first()
    
    def get_entries(self, page: int = 1, per_page: int = 10) -> Tuple[List[Entry], int]:
        """Get entries with pagination"""
        
        query = self.db.query(Entry)
        total = query.count()
        
        entries = query.offset((page - 1) * per_page).limit(per_page).all()
        
        return entries, total
    
    def update_entry_file_path(self, entry_id: UUID, file_path: str) -> Optional[Entry]:
        """Update entry file path"""
        
        entry = self.get_entry(entry_id)
        if not entry:
            return None
        
        entry.file_path = file_path
        self.db.commit()
        self.db.refresh(entry)
        
        return entry
    
    def update_entry_status(self, entry_id: UUID, status: EntryStatus) -> Optional[Entry]:
        """Update entry status"""
        
        entry = self.get_entry(entry_id)
        if not entry:
            return None
        
        entry.status = status
        self.db.commit()
        self.db.refresh(entry)
        
        return entry
    
    def update_entry_transcript(self, entry_id: UUID, transcript: str) -> Optional[Entry]:
        """Update entry transcript"""
        
        entry = self.get_entry(entry_id)
        if not entry:
            return None
        
        entry.transcript = transcript
        entry.status = EntryStatus.READY
        self.db.commit()
        self.db.refresh(entry)
        
        return entry
    
    def update_entry_summary(self, entry_id: UUID, summary: str) -> Optional[Entry]:
        """Update entry summary"""
        
        entry = self.get_entry(entry_id)
        if not entry:
            return None
        
        entry.summary = summary
        self.db.commit()
        self.db.refresh(entry)
        
        return entry
    
    def update_entry_error(self, entry_id: UUID, error_message: str) -> Optional[Entry]:
        """Update entry with error message"""
        
        entry = self.get_entry(entry_id)
        if not entry:
            return None
        
        entry.error_message = error_message
        entry.status = EntryStatus.NEW  # Reset to NEW for retry
        self.db.commit()
        self.db.refresh(entry)
        
        return entry
    
    def delete_entry(self, entry_id: UUID) -> bool:
        """Delete entry and associated file"""
        
        entry = self.get_entry(entry_id)
        if not entry:
            return False
        
        # Delete associated file if it exists
        if entry.file_path and os.path.exists(entry.file_path):
            try:
                os.remove(entry.file_path)
            except OSError:
                pass  # File might be in use or already deleted
        
        # Delete database entry
        self.db.delete(entry)
        self.db.commit()
        
        return True