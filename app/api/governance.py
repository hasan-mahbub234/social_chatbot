"""Governance API — logs, policy evaluation, PII reports."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.governance_log import GovernanceLog
from app.governance.governance_service import governance_service
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/governance", tags=["governance"])


class EvaluateRequest(BaseModel):
    text: str
    advanced: bool = False


@router.post("/evaluate")
async def evaluate_text(
    req: EvaluateRequest,
    current_user: User = Depends(get_current_user),
):
    """Evaluate text through the governance pipeline."""
    if not current_user.organization_id:
        raise HTTPException(status_code=400, detail="User must belong to an organization")

    result = await governance_service.evaluate(
        req.text,
        organization_id=str(current_user.organization_id),
        advanced=req.advanced,
    )
    return result


@router.get("/logs")
async def get_governance_logs(
    limit: int = Query(50, ge=1, le=200),
    policy_type: Optional[str] = None,
    action: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get governance logs for the organization."""
    if not current_user.organization_id:
        raise HTTPException(status_code=400, detail="User must belong to an organization")

    query = db.query(GovernanceLog).filter(
        GovernanceLog.organization_id == current_user.organization_id
    )
    if policy_type:
        query = query.filter(GovernanceLog.policy_type == policy_type)
    if action:
        query = query.filter(GovernanceLog.action_taken == action)

    logs = query.order_by(GovernanceLog.created_at.desc()).limit(limit).all()

    return [
        {
            "id": str(log.id),
            "policy_name": log.policy_name,
            "policy_type": log.policy_type,
            "action_taken": log.action_taken,
            "severity": log.severity,
            "description": log.description,
            "is_blocked": log.is_blocked,
            "is_escalated": log.is_escalated,
            "created_at": log.created_at.isoformat(),
        }
        for log in logs
    ]


@router.get("/stats")
async def get_governance_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get governance statistics for the organization."""
    if not current_user.organization_id:
        raise HTTPException(status_code=400, detail="User must belong to an organization")

    from sqlalchemy import func
    org_id = current_user.organization_id

    total = db.query(func.count(GovernanceLog.id)).filter(
        GovernanceLog.organization_id == org_id
    ).scalar() or 0

    blocked = db.query(func.count(GovernanceLog.id)).filter(
        GovernanceLog.organization_id == org_id,
        GovernanceLog.is_blocked == True,
    ).scalar() or 0

    by_type = db.query(
        GovernanceLog.policy_type,
        func.count(GovernanceLog.id).label("count"),
    ).filter(
        GovernanceLog.organization_id == org_id
    ).group_by(GovernanceLog.policy_type).all()

    return {
        "total_evaluations": total,
        "blocked_count": blocked,
        "block_rate": round(blocked / total, 4) if total > 0 else 0.0,
        "by_policy_type": {r.policy_type: r.count for r in by_type},
    }
