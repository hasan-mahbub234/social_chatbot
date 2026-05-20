"""Cache entry model for semantic cache persistence."""
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Integer
from sqlalchemy.dialects.postgresql import UUID, ARRAY, NUMERIC
from datetime import datetime
import uuid
from app.core.database import Base


class CacheEntry(Base):
    """Persistent semantic cache entry."""

    __tablename__ = "cache_entries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id"), nullable=True)

    # Query and response
    query_hash = Column(String(64), unique=True, nullable=False, index=True)
    query_text = Column(Text, nullable=False)
    response_text = Column(Text, nullable=False)

    # Embedding vector for similarity lookup
    query_embedding = Column(ARRAY(NUMERIC), nullable=True)

    # Metadata
    model_used = Column(String(100), nullable=True)
    hallucination_score = Column(NUMERIC(5, 2), nullable=True)

    # Stats
    hit_count = Column(Integer, default=0)
    last_accessed_at = Column(DateTime, nullable=True)

    # TTL
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<CacheEntry {self.query_hash[:8]}... hits={self.hit_count}>"
