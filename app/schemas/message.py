"""Message schemas."""
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List, Literal
from datetime import datetime
from uuid import UUID
from decimal import Decimal


class MessageBase(BaseModel):
    """Base message schema."""
    role: Literal["user", "assistant", "system"]
    content: str = Field(..., min_length=1, max_length=50000)


class MessageCreate(MessageBase):
    """Message creation schema."""
    conversation_id: UUID


class MessageUpdate(BaseModel):
    """Message update schema."""
    content: Optional[str] = None


class MessageResponse(MessageBase):
    """Message response schema."""
    id: UUID
    conversation_id: UUID
    tokens_used: int = 0
    cost: Decimal = Decimal("0.0")
    sources: Dict[str, Any] = {}
    is_hallucination_checked: bool = False
    hallucination_score: Optional[Decimal] = None
    created_at: datetime

    class Config:
        from_attributes = True


class BatchMessageResponse(BaseModel):
    """Batch message response."""
    messages: List[MessageResponse]
    total_cost: Decimal
    total_tokens: int
