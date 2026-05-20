"""AI Agent model."""
from sqlalchemy import Column, String, DateTime, ForeignKey, JSON, Boolean, Text, Enum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from app.core.database import Base


class Agent(Base):
    """AI Agent model."""

    __tablename__ = "agents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    description = Column(String(1000), nullable=True)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    
    # Agent Configuration
    model = Column(String(100), default="gpt-4-turbo")
    system_prompt = Column(Text, nullable=True)
    temperature = Column(String(10), default="0.7")
    max_tokens = Column(String(10), default="2000")
    
    # Features
    enable_rag = Column(Boolean, default=True)
    enable_semantic_cache = Column(Boolean, default=True)
    enable_risk_assessment = Column(Boolean, default=True)
    enable_escalation = Column(Boolean, default=True)
    
    # Status
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    extra_data = Column("extra_data", JSONB, default={})

    # Relationships
    organization = relationship("Organization", back_populates="agents")
    conversations = relationship("Conversation", back_populates="agent")
    risk_policies = relationship("RiskPolicy", back_populates="agent")
    escalations = relationship("Escalation", back_populates="agent")

    def __repr__(self):
        return f"<Agent {self.name}>"


class RiskPolicy(Base):
    """Risk policy for agents."""

    __tablename__ = "risk_policies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id"), nullable=False)
    
    # Policy Configuration
    name = Column(String(255), nullable=False)
    description = Column(String(1000), nullable=True)
    policy_type = Column(String(50))  # cost_control, data_leakage, pii_detection
    risk_level = Column(String(50))  # low, medium, high, critical
    
    # Rules
    rules = Column(JSONB, default={})
    thresholds = Column(JSONB, default={})
    
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    agent = relationship("Agent", back_populates="risk_policies")

    def __repr__(self):
        return f"<RiskPolicy {self.name}>"
