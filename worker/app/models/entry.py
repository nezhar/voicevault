from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Enum as SQLEnum,
    Float,
    Integer,
    String,
    Text,
)
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
    user_id = Column(UUID(as_uuid=True), nullable=True)
    project_id = Column(UUID(as_uuid=True), nullable=True)
    transcript = Column(Text, nullable=True)
    transcript_words = Column(Text, nullable=True)
    transcript_segments = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    speakers = Column(Text, nullable=True)
    additional_context = Column(Text, nullable=True)
    language = Column(String(16), nullable=True)
    error_message = Column(Text, nullable=True)
    # Mirrors api/app/models/entry.py — the two containers share no package.
    file_size_bytes = Column(BigInteger, nullable=True)
    duration_seconds = Column(Float, nullable=True)
    word_count = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
