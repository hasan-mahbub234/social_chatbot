"""Usage tracking models."""
from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, Boolean, Numeric
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from app.core.database import Base


class UsageLog(Base):
    """API usage log per request."""

    __tablename__ = "usage_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id"), nullable=True)

    endpoint = Column(String(255), nullable=False)
    method = Column(String(10), nullable=False)
    status_code = Column(Integer, nullable=False)

    tokens_used = Column(Integer, default=0)
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    cost = Column(Numeric(10, 6), default=0.0)

    response_time_ms = Column(Integer, default=0)
    extra_data = Column("extra_data", JSONB, default={})

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User", back_populates="usage_logs")

    def __repr__(self):
        return f"<UsageLog {self.endpoint}>"


class APIKey(Base):
    """API key for programmatic access."""

    __tablename__ = "api_keys"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    name = Column(String(255), nullable=False)
    key = Column(String(255), unique=True, nullable=False, index=True)
    permissions = Column(JSONB, default={})

    is_active = Column(Boolean, default=True)
    last_used_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=True)

    # Relationships
    user = relationship("User", back_populates="api_keys")

    def __repr__(self):
        return f"<APIKey {self.name}>"


class CostTracking(Base):
    """Monthly cost tracking per organization."""

    __tablename__ = "cost_tracking"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id"), nullable=True)

    month = Column(String(7), nullable=False)  # YYYY-MM
    date = Column(DateTime, nullable=False)

    total_cost = Column(Numeric(10, 4), default=0.0)
    model_cost = Column(Numeric(10, 4), default=0.0)
    embedding_cost = Column(Numeric(10, 4), default=0.0)

    total_tokens = Column(Integer, default=0)
    total_requests = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<CostTracking {self.month}>"
