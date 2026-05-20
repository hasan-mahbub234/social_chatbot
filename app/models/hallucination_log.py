"""Hallucination log model."""
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Boolean, Numeric
from sqlalchemy.dialects.postgresql import UUID, JSONB
from datetime import datetime
import uuid
from app.core.database import Base


class HallucinationLog(Base):
    """Hallucination detection and validation log."""

    __tablename__ = "hallucination_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=True)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id"), nullable=True)
    message_id = Column(UUID(as_uuid=True), ForeignKey("messages.id"), nullable=True)

    # Detection details
    query_snippet = Column(Text, nullable=True)
    response_snippet = Column(Text, nullable=False)
    confidence_score = Column(Numeric(5, 2), nullable=False)
    risk_level = Column(String(50), nullable=False)  # minimal, low, medium, high
    detection_method = Column(String(50), nullable=False)  # heuristic, embedding, llm

    # Findings
    findings = Column(JSONB, default=[])

    # Resolution
    action_taken = Column(String(50), default="logged")  # logged, regenerated, escalated, blocked
    is_resolved = Column(Boolean, default=False)
    resolution_notes = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    resolved_at = Column(DateTime, nullable=True)

    def __repr__(self):
        return f"<HallucinationLog score={self.confidence_score} level={self.risk_level}>"
