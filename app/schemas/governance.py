"""Governance schemas."""
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from datetime import datetime
from uuid import UUID


class GovernanceCheckResult(BaseModel):
    allowed: bool
    risk_level: str
    policy_flags: List[str] = []
    reason: str = ""
    action: str = "allow"  # allow, warn, block


class GovernanceLogResponse(BaseModel):
    id: UUID
    policy_name: str
    policy_type: str
    action_taken: str
    severity: str
    description: str
    is_blocked: bool
    is_escalated: bool
    created_at: datetime

    class Config:
        from_attributes = True


class PolicyCreate(BaseModel):
    name: str
    description: Optional[str] = None
    policy_type: str
    rules: List[Dict[str, Any]] = []
    enabled: bool = True


class PIIDetectionResult(BaseModel):
    has_pii: bool
    pii_types: List[str] = []
    findings: Dict[str, List[str]] = {}
    risk_level: str = "low"


class ModerationResult(BaseModel):
    is_safe: bool
    categories: Dict[str, bool] = {}
    scores: Dict[str, float] = {}
    flagged: bool = False
