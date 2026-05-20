"""Risk assessment model."""
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Boolean, Numeric
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from datetime import datetime
import uuid
from app.core.database import Base


class RiskAssessment(Base):
    """Risk assessment record per message/conversation."""

    __tablename__ = "risk_assessments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=True)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id"), nullable=True)
    message_id = Column(UUID(as_uuid=True), ForeignKey("messages.id"), nullable=True)

    # Assessment details
    assessment_type = Column(String(50), nullable=False)  # cost, pii, leakage, fraud, abuse
    risk_level = Column(String(50), nullable=False)  # low, medium, high, critical
    risk_score = Column(Numeric(5, 2), nullable=False, default=0.0)

    # Findings
    findings = Column(JSONB, default=[])
    recommended_actions = Column(ARRAY(String), default=[])

    # Escalation
    is_escalated = Column(Boolean, default=False)
    escalation_id = Column(UUID(as_uuid=True), ForeignKey("escalations.id"), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<RiskAssessment {self.assessment_type} level={self.risk_level}>"
