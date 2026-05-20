"""Pydantic schemas for conversation operations."""
from pydantic import BaseModel, Field
from datetime import datetime
from uuid import UUID
from typing import Optional, List, Dict, Any


class MessageCreate(BaseModel):
    """Message creation schema."""
    role: str  # user, assistant
    content: str


class MessageResponse(BaseModel):
    """Message response schema."""
    id: UUID
    role: str
    content: str
    tokens_used: int
    cost: float
    hallucination_score: Optional[float] = None
    is_hallucination_checked: bool
    created_at: datetime

    class Config:
        from_attributes = True


class ConversationCreate(BaseModel):
    """Conversation creation schema."""
    agent_id: UUID
    title: Optional[str] = None


class ConversationUpdate(BaseModel):
    """Conversation update schema."""
    title: Optional[str] = None
    is_archived: Optional[bool] = None


class ConversationResponse(BaseModel):
    """Conversation response schema."""
    id: UUID
    agent_id: UUID
    title: Optional[str] = None
    summary: Optional[str] = None
    is_archived: bool
    created_at: datetime
    updated_at: datetime
    message_count: Optional[int] = 0

    class Config:
        from_attributes = True


class ConversationDetailResponse(ConversationResponse):
    """Detailed conversation response with messages."""
    messages: List[MessageResponse]


class ChatRequest(BaseModel):
    """Chat request schema."""
    conversation_id: Optional[UUID] = None
    agent_id: UUID
    message: str = Field(..., min_length=1, max_length=10000)
    context: Optional[Dict[str, Any]] = None


class ChatResponse(BaseModel):
    """Chat response schema."""
    conversation_id: UUID
    message_id: UUID
    role: str
    content: str
    tokens_used: int
    cost: float
    sources: Dict[str, Any]
    created_at: datetime


class RiskAssessmentResponse(BaseModel):
    """Risk assessment response schema."""
    id: UUID
    assessment_type: str
    risk_level: str
    score: float
    findings: Dict[str, Any]
    recommended_actions: List[str]
    is_escalated: bool
    created_at: datetime

    class Config:
        from_attributes = True


class EscalationResponse(BaseModel):
    """Escalation response schema."""
    id: UUID
    reason: str
    severity: str
    status: str
    assigned_to: Optional[UUID] = None
    context: Dict[str, Any]
    resolution_notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
