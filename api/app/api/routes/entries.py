from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
from datetime import datetime
import os
import shutil
from pathlib import Path
from loguru import logger

from app.db.database import get_db
from app.models.entry import Entry, EntryStatus, SourceType
from app.models.schemas import (
    EntryResponse, EntryCreate, EntryStatusUpdate, EntryList,
    ChatRequest, ChatResponse, SummaryResponse
)
from app.services.entry_service import EntryService
from app.services.s3_service import S3Service
from app.services.chat_service import ChatService
from app.core.config import settings
from app.core.auth import get_current_user

router = APIRouter()

@router.post("/upload", response_model=EntryResponse)
async def upload_file(
    title: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: bool = Depends(get_current_user)
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
    
    if file_size > settings.max_upload_size:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size is {settings.max_upload_size} bytes."
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
    db: Session = Depends(get_db),
    current_user: bool = Depends(get_current_user)
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
    per_page: int = 12,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: bool = Depends(get_current_user)
):
    """Get all entries with pagination and optional search"""

    entry_service = EntryService(db)
    entries, total = entry_service.get_entries(page=page, per_page=per_page, search=search)

    return EntryList(
        entries=[EntryResponse.from_orm(entry) for entry in entries],
        total=total,
        page=page,
        per_page=per_page
    )

@router.get("/{entry_id}", response_model=EntryResponse)
async def get_entry(
    entry_id: UUID,
    db: Session = Depends(get_db),
    current_user: bool = Depends(get_current_user)
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
    db: Session = Depends(get_db),
    current_user: bool = Depends(get_current_user)
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
    db: Session = Depends(get_db),
    current_user: bool = Depends(get_current_user)
):
    """Delete entry and associated file"""
    
    entry_service = EntryService(db)
    success = entry_service.delete_entry(entry_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="Entry not found")
    
    return {"message": "Entry deleted successfully"}

@router.post("/{entry_id}/chat", response_model=ChatResponse)
async def chat_with_entry(
    entry_id: UUID,
    chat_request: ChatRequest,
    db: Session = Depends(get_db),
    current_user: bool = Depends(get_current_user)
):
    """Chat about an entry's transcript using Groq Llama 3.1"""
    
    # Get the entry
    entry_service = EntryService(db)
    entry = entry_service.get_entry(entry_id)
    
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    
    if not entry.transcript:
        raise HTTPException(
            status_code=400, 
            detail="Entry must have a transcript to chat about. Please wait for processing to complete."
        )
    
    if entry.status != EntryStatus.READY:
        raise HTTPException(
            status_code=400,
            detail=f"Entry is not ready for chat. Current status: {entry.status.value}"
        )
    
    # Initialize chat service
    try:
        chat_service = ChatService()
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    # Convert conversation history to dict format
    conversation_history = None
    if chat_request.conversation_history:
        conversation_history = [
            {"role": msg.role, "content": msg.content}
            for msg in chat_request.conversation_history
        ]
    
    try:
        # Generate response
        response_message = await chat_service.chat_with_entry(
            entry=entry,
            user_message=chat_request.message,
            conversation_history=conversation_history
        )
        
        return ChatResponse(
            message=response_message,
            timestamp=datetime.utcnow()
        )
        
    except Exception as e:
        logger.error(f"Chat error for entry {entry_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to generate chat response")

@router.post("/{entry_id}/summary", response_model=SummaryResponse)
async def generate_entry_summary(
    entry_id: UUID,
    db: Session = Depends(get_db),
    current_user: bool = Depends(get_current_user)
):
    """Generate an AI summary of the entry's transcript"""
    
    # Get the entry
    entry_service = EntryService(db)
    entry = entry_service.get_entry(entry_id)
    
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    
    if not entry.transcript:
        raise HTTPException(
            status_code=400,
            detail="Entry must have a transcript to summarize"
        )
    
    if entry.status != EntryStatus.READY:
        raise HTTPException(
            status_code=400,
            detail=f"Entry is not ready for summary. Current status: {entry.status.value}"
        )
    
    # Initialize chat service
    try:
        chat_service = ChatService()
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    try:
        # Generate summary
        summary = await chat_service.generate_summary(entry)
        
        # Update entry with summary
        entry_service.update_entry_summary(entry_id, summary)
        
        return SummaryResponse(
            summary=summary,
            timestamp=datetime.utcnow()
        )
        
    except Exception as e:
        logger.error(f"Summary generation error for entry {entry_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to generate summary")
