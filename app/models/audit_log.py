"""Audit log model."""
from sqlalchemy import Column, String, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from app.core.database import Base


class AuditLog(Base):
    """Audit log for all user and system actions."""

    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=True)

    action = Column(String(255), nullable=False)
    resource_type = Column(String(100), nullable=False)
    resource_id = Column(UUID(as_uuid=True), nullable=True)

    # Details
    changes = Column(JSONB, default={})
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User", back_populates="audit_logs")

    def __repr__(self):
        return f"<AuditLog {self.action} on {self.resource_type}>"
