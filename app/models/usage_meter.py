"""Usage metering and quota tracking models."""
from sqlalchemy import Column, String, DateTime, Boolean, Numeric, Integer, ForeignKey, Text, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from datetime import datetime
import uuid
from app.core.database import Base


class UsageMeter(Base):
    """Real-time usage meter per organization per billing period."""

    __tablename__ = "usage_meters"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)

    # Billing period
    period = Column(String(7), nullable=False)   # YYYY-MM

    # Conversation usage
    conversations_count = Column(Integer, default=0)

    # Token usage
    total_tokens = Column(Integer, default=0)
    gpt4o_tokens = Column(Integer, default=0)
    gpt4o_mini_tokens = Column(Integer, default=0)
    embedding_tokens = Column(Integer, default=0)

    # Voice
    voice_minutes = Column(Numeric(10, 2), default=0.0)

    # Storage (MB)
    storage_mb = Column(Numeric(10, 2), default=0.0)

    # API calls
    api_calls = Column(Integer, default=0)

    # Cost tracking
    total_cost_usd = Column(Numeric(12, 6), default=0.0)
    gpt4o_cost_usd = Column(Numeric(12, 6), default=0.0)
    gpt4o_mini_cost_usd = Column(Numeric(12, 6), default=0.0)
    embedding_cost_usd = Column(Numeric(12, 6), default=0.0)
    voice_cost_usd = Column(Numeric(12, 6), default=0.0)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ix_usage_meters_org_period", "organization_id", "period", unique=True),
    )

    def __repr__(self):
        return f"<UsageMeter org={self.organization_id} period={self.period}>"


class TenantUsage(Base):
    """Granular per-request usage event for analytics."""

    __tablename__ = "tenant_usage"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id"), nullable=True)
    conversation_id = Column(UUID(as_uuid=True), nullable=True)

    # Usage type
    usage_type = Column(String(50), nullable=False)   # chat, embedding, voice_transcribe, voice_tts, api_call
    model = Column(String(100), nullable=True)

    # Metrics
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)
    cost_usd = Column(Numeric(12, 6), default=0.0)
    duration_ms = Column(Integer, default=0)

    # Voice
    voice_seconds = Column(Numeric(10, 2), default=0.0)

    # Cache
    from_cache = Column(Boolean, default=False)

    # Billing period
    period = Column(String(7), nullable=False)   # YYYY-MM

    extra_data = Column("extra_data", JSONB, default={})
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_tenant_usage_org_period", "organization_id", "period"),
        Index("ix_tenant_usage_created", "created_at"),
    )

    def __repr__(self):
        return f"<TenantUsage org={self.organization_id} type={self.usage_type}>"


class QuotaEvent(Base):
    """Quota enforcement event log."""

    __tablename__ = "quota_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)

    quota_type = Column(String(50), nullable=False)   # conversations, tokens, api_calls, storage, voice
    event_type = Column(String(50), nullable=False)   # soft_limit_hit, hard_limit_hit, budget_alert, reset
    current_value = Column(Numeric(15, 2), nullable=False)
    limit_value = Column(Numeric(15, 2), nullable=False)
    percentage_used = Column(Numeric(5, 2), nullable=False)

    message = Column(Text, nullable=True)
    extra_data = Column("extra_data", JSONB, default={})

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<QuotaEvent org={self.organization_id} type={self.quota_type} event={self.event_type}>"


class APIUsage(Base):
    """Per-endpoint API usage tracking."""

    __tablename__ = "api_usage"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    endpoint = Column(String(255), nullable=False)
    method = Column(String(10), nullable=False)
    status_code = Column(Integer, nullable=False)
    response_time_ms = Column(Integer, default=0)

    # Rate limiting
    rate_limit_key = Column(String(255), nullable=True)
    was_rate_limited = Column(Boolean, default=False)

    # Billing period
    period = Column(String(7), nullable=False)

    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)
    request_id = Column(String(100), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_api_usage_org_period", "organization_id", "period"),
        Index("ix_api_usage_created", "created_at"),
    )

    def __repr__(self):
        return f"<APIUsage {self.method} {self.endpoint} status={self.status_code}>"
