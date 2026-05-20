"""Uploaded file model."""
from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, Boolean, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from datetime import datetime
import uuid
from app.core.database import Base


class UploadedFile(Base):
    """Uploaded file for RAG and context."""

    __tablename__ = "uploaded_files"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id"), nullable=True)
    
    # File metadata
    filename = Column(String(255), nullable=False)
    file_type = Column(String(50), nullable=False)  # pdf, txt, docx, etc
    file_size = Column(Integer, nullable=False)  # in bytes
    
    # Storage
    storage_path = Column(String(500), nullable=False)
    s3_key = Column(String(500), nullable=True)
    
    # Content
    content_preview = Column(Text, nullable=True)  # First 500 chars
    is_indexed = Column(Boolean, default=False)
    
    # Processing
    processed_chunks = Column(String(10), default="0")
    
    extra_data = Column("extra_data", JSONB, default={})
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<UploadedFile {self.filename}>"
