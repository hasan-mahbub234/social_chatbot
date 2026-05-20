"""Risk schemas."""
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from datetime import datetime
from uuid import UUID


class RiskAssessmentResult(BaseModel):
    risk_level: str
    risk_score: float
    findings: List[str] = []
    recommended_actions: List[str] = []
    is_escalated: bool = False
    pii_detected: Optional[Dict[str, List[str]]] = None


class ComprehensiveRiskResult(BaseModel):
    overall_risk_level: str
    is_escalated: bool
    assessments: Dict[str, RiskAssessmentResult]


class RiskAssessmentResponse(BaseModel):
    id: UUID
    assessment_type: str
    risk_level: str
    risk_score: float
    findings: List[Any]
    recommended_actions: List[str]
    is_escalated: bool
    created_at: datetime

    class Config:
        from_attributes = True


class EscalationCreate(BaseModel):
    reason: str
    severity: str
    context: Dict[str, Any] = {}


class EscalationResponse(BaseModel):
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
