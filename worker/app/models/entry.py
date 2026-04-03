from sqlalchemy import Boolean, Column, DateTime, Enum as SQLEnum, String, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
from enum import Enum
import uuid

Base = declarative_base()

class EntryStatus(str, Enum):
    NEW = "NEW"
    IN_PROGRESS = "IN_PROGRESS"
    READY = "READY"
    COMPLETE = "COMPLETE"
    ERROR = "ERROR"

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
    archived = Column(Boolean, nullable=False, default=False)
    transcript = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
