"""Governance log model."""
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Boolean
from sqlalchemy.dialects.postgresql import UUID, JSONB
from datetime import datetime
import uuid
from app.core.database import Base


class GovernanceLog(Base):
    """Governance and compliance event log."""

    __tablename__ = "governance_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=True)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id"), nullable=True)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id"), nullable=True)

    # Policy details
    policy_name = Column(String(255), nullable=False)
    policy_type = Column(String(50), nullable=False)  # pii, jailbreak, moderation, compliance

    # Result
    action_taken = Column(String(50), nullable=False)  # allow, warn, block
    severity = Column(String(50), nullable=False)  # info, warning, critical
    description = Column(Text, nullable=False)

    # Input/output snapshot
    input_snippet = Column(Text, nullable=True)
    details = Column(JSONB, default={})

    # Flags
    is_blocked = Column(Boolean, default=False)
    is_escalated = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<GovernanceLog {self.policy_name} action={self.action_taken}>"
