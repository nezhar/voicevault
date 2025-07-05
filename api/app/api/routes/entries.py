from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.orm import Session
from typing import List
from uuid import UUID
import os
import shutil
from pathlib import Path

from app.db.database import get_db
from app.models.entry import Entry, EntryStatus, SourceType
from app.models.schemas import EntryResponse, EntryCreate, EntryStatusUpdate, EntryList
from app.services.entry_service import EntryService
from app.services.s3_service import S3Service
from app.core.config import settings

router = APIRouter()

@router.post("/upload", response_model=EntryResponse)
async def upload_file(
    title: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """Upload audio or video file"""
    
    # Validate file type
    file_extension = file.filename.split('.')[-1].lower()
    supported_formats = settings.supported_audio_formats + settings.supported_video_formats
    
    if file_extension not in supported_formats:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format. Supported: {', '.join(supported_formats)}"
        )
    
    # Validate file size
    file.file.seek(0, 2)  # Seek to end
    file_size = file.file.tell()
    file.file.seek(0)  # Reset to beginning
    
    if file_size > settings.max_file_size:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Max size: {settings.max_file_size} bytes"
        )
    
    # Create entry in database first
    entry_service = EntryService(db)
    entry = entry_service.create_entry(
        title=title,
        source_type=SourceType.UPLOAD,
        filename=file.filename
    )
    
    # Initialize S3 service
    s3_service = S3Service()
    
    # Generate S3 key for the file
    s3_key = f"uploads/{entry.id}.{file_extension}"
    
    try:
        # Upload file to S3
        success = s3_service.upload_file(
            file.file, 
            s3_key,
            content_type=file.content_type
        )
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to upload file to S3")
        
        # Update entry with S3 key as file path
        entry = entry_service.update_entry_file_path(entry.id, s3_key)
        
        # Start background processing
        # TODO: Implement background task for ASR processing
        
        return EntryResponse.from_orm(entry)
        
    except Exception as e:
        # Clean up S3 file if database operation fails
        s3_service.delete_file(s3_key)
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")

@router.post("/url", response_model=EntryResponse)
async def create_from_url(
    entry_data: EntryCreate,
    db: Session = Depends(get_db)
):
    """Create entry from URL"""
    
    if not entry_data.source_url:
        raise HTTPException(status_code=400, detail="source_url is required")
    
    # TODO: Validate URL and check if it's from supported services
    
    entry_service = EntryService(db)
    entry = entry_service.create_entry(
        title=entry_data.title,
        source_type=SourceType.URL,
        source_url=str(entry_data.source_url)
    )
    
    # TODO: Start background processing for URL download and ASR
    
    return EntryResponse.from_orm(entry)

@router.get("/", response_model=EntryList)
async def get_entries(
    page: int = 1,
    per_page: int = 10,
    db: Session = Depends(get_db)
):
    """Get all entries with pagination"""
    
    entry_service = EntryService(db)
    entries, total = entry_service.get_entries(page=page, per_page=per_page)
    
    return EntryList(
        entries=[EntryResponse.from_orm(entry) for entry in entries],
        total=total,
        page=page,
        per_page=per_page
    )

@router.get("/{entry_id}", response_model=EntryResponse)
async def get_entry(
    entry_id: UUID,
    db: Session = Depends(get_db)
):
    """Get specific entry by ID"""
    
    entry_service = EntryService(db)
    entry = entry_service.get_entry(entry_id)
    
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    
    return EntryResponse.from_orm(entry)

@router.put("/{entry_id}/status", response_model=EntryResponse)
async def update_entry_status(
    entry_id: UUID,
    status_update: EntryStatusUpdate,
    db: Session = Depends(get_db)
):
    """Update entry status"""
    
    entry_service = EntryService(db)
    entry = entry_service.update_entry_status(entry_id, status_update.status)
    
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    
    return EntryResponse.from_orm(entry)

@router.delete("/{entry_id}")
async def delete_entry(
    entry_id: UUID,
    db: Session = Depends(get_db)
):
    """Delete entry and associated file"""
    
    entry_service = EntryService(db)
    success = entry_service.delete_entry(entry_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="Entry not found")
    
    return {"message": "Entry deleted successfully"}