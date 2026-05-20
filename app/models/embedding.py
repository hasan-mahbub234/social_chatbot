"""Embedding model for semantic search."""
from sqlalchemy import Column, String, DateTime, ForeignKey, NUMERIC
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from app.core.database import Base


class Embedding(Base):
    """Embedding model for messages and documents."""

    __tablename__ = "embeddings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Content reference
    content_id = Column(UUID(as_uuid=True), nullable=False)
    content_type = Column(String(50), nullable=False)  # message, document, query
    
    # Embedding vector
    vector = Column(ARRAY(NUMERIC), nullable=False, index=True)
    
    # Metadata
    model_name = Column(String(100), default="text-embedding-3-small")
    dimensions = Column(String(10), default="1536")
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<Embedding {self.content_type}:{self.content_id}>"
