from datetime import datetime

from sqlalchemy import Column, DateTime, String, Text

from app.db.database import Base


class SystemPrompt(Base):
    __tablename__ = "system_prompts"

    task = Column(String(50), primary_key=True)
    body = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
