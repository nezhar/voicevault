from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
from enum import Enum
import uuid

from app.db.database import Base


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
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,  # NULL only for legacy rows
        index=True,
    )
    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,  # NULL = private
        index=True,
    )
    transcript = Column(Text, nullable=True)
    transcript_words = Column(Text, nullable=True)
    transcript_segments = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    speakers = Column(Text, nullable=True)
    additional_context = Column(Text, nullable=True)
    language = Column(String(16), nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    owner = relationship("User", lazy="joined")
