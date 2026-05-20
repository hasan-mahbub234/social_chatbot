"""Escalation model."""
from sqlalchemy import Column, String, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from app.core.database import Base


class Escalation(Base):
    """Escalation record for complex issues."""

    __tablename__ = "escalations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id"), nullable=True)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id"), nullable=True)

    reason = Column(Text, nullable=False)
    severity = Column(String(50), nullable=False)  # low, medium, high, critical
    status = Column(String(50), default="pending")  # pending, reviewed, resolved

    assigned_to = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    resolution_notes = Column(Text, nullable=True)
    context = Column(JSONB, default={})

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)

    # Relationships
    agent = relationship("Agent", back_populates="escalations")

    def __repr__(self):
        return f"<Escalation {self.id}>"
