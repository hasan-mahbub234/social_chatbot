"""Hallucination schemas."""
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime
from uuid import UUID


class HallucinationCheckResult(BaseModel):
    hallucination_score: float
    risk_level: str  # minimal, low, medium, high
    findings: List[str] = []
    is_hallucination_likely: bool = False
    recommended_actions: List[str] = []
    confidence: float = 1.0


class HallucinationLogResponse(BaseModel):
    id: UUID
    confidence_score: float
    risk_level: str
    detection_method: str
    findings: List[Any]
    action_taken: str
    is_resolved: bool
    created_at: datetime

    class Config:
        from_attributes = True


class RegenerationRequest(BaseModel):
    original_query: str
    original_response: str
    hallucination_score: float
    context: Optional[List[str]] = None
    max_attempts: int = 2
