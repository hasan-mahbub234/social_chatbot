"""Feature flag model for per-plan and per-tenant feature gating."""
from sqlalchemy import Column, String, DateTime, Boolean, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from datetime import datetime
import uuid
from app.core.database import Base


class FeatureFlag(Base):
    """Feature flag — can be scoped to a plan or overridden per organization."""

    __tablename__ = "feature_flags"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Flag identity
    key = Column(String(100), nullable=False, index=True)   # e.g. "voice_access", "gpt4o_access"
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Scope: plan-level default
    plan_name = Column(String(50), nullable=True)   # starter, growth, enterprise, None=global

    # Scope: org-level override (nullable = plan default applies)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=True)

    # Value
    is_enabled = Column(Boolean, default=False)
    config = Column(JSONB, default={})   # optional config payload

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<FeatureFlag {self.key} plan={self.plan_name} org={self.organization_id} enabled={self.is_enabled}>"
