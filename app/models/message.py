"""Message model (standalone)."""
from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, Boolean, Text, Numeric
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from app.core.database import Base


class Message(Base):
    """Chat message model."""

    __tablename__ = "messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id"), nullable=False)

    role = Column(String(50), nullable=False)  # user, assistant, system
    content = Column(Text, nullable=False)

    # Token & cost tracking
    tokens_used = Column(Integer, default=0)
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    cost = Column(Numeric(10, 6), default=0.0)

    # Model used
    model_used = Column(String(100), nullable=True)

    # Source tracking for RAG
    sources = Column(JSONB, default={})

    # Hallucination tracking
    is_hallucination_checked = Column(Boolean, default=False)
    hallucination_score = Column(Numeric(5, 2), nullable=True)

    # Cache hit
    from_cache = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    conversation = relationship("Conversation", back_populates="messages")

    def __repr__(self):
        return f"<Message {self.id} role={self.role}>"
