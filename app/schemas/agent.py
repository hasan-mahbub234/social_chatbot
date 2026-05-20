"""Pydantic schemas for agent operations."""
from pydantic import BaseModel, Field
from datetime import datetime
from uuid import UUID
from typing import Optional, Dict, Any


class AgentConfigBase(BaseModel):
    """Base agent configuration."""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    model: str = "gpt-4-turbo"
    system_prompt: Optional[str] = None
    temperature: float = Field(0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(2000, ge=1, le=8000)


class AgentFeatures(BaseModel):
    """Agent features configuration."""
    enable_rag: bool = True
    enable_semantic_cache: bool = True
    enable_risk_assessment: bool = True
    enable_escalation: bool = True


class AgentCreate(AgentConfigBase, AgentFeatures):
    """Agent creation schema."""
    organization_id: UUID


class AgentUpdate(BaseModel):
    """Agent update schema."""
    name: Optional[str] = None
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    enable_rag: Optional[bool] = None
    enable_semantic_cache: Optional[bool] = None
    enable_risk_assessment: Optional[bool] = None
    enable_escalation: Optional[bool] = None


class AgentResponse(AgentConfigBase, AgentFeatures):
    """Agent response schema."""
    id: UUID
    organization_id: UUID
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class RiskPolicyBase(BaseModel):
    """Base risk policy schema."""
    name: str
    description: Optional[str] = None
    policy_type: str  # cost_control, data_leakage, pii_detection
    risk_level: str  # low, medium, high, critical
    rules: Dict[str, Any]
    thresholds: Dict[str, Any]


class RiskPolicyCreate(RiskPolicyBase):
    """Risk policy creation schema."""
    agent_id: UUID


class RiskPolicyResponse(RiskPolicyBase):
    """Risk policy response schema."""
    id: UUID
    agent_id: UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
