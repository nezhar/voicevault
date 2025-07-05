from sqlalchemy import Column, String, DateTime, Text, Enum as SQLEnum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
from enum import Enum
import uuid

Base = declarative_base()

class EntryStatus(str, Enum):
    NEW = "new"
    IN_PROGRESS = "in_progress"
    READY = "ready"
    COMPLETE = "complete"
    ERROR = "error"

class SourceType(str, Enum):
    UPLOAD = "upload"
    URL = "url"

class Entry(Base):
    __tablename__ = "entries"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(255), nullable=False)
    source_type = Column(SQLEnum(SourceType), nullable=False)
    source_url = Column(String(1024), nullable=True)
    file_path = Column(String(512), nullable=True)
    filename = Column(String(255), nullable=True)
    status = Column(SQLEnum(EntryStatus), default=EntryStatus.NEW)
    transcript = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)