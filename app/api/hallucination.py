"""Hallucination API — logs and detection statistics."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional
from pydantic import BaseModel
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.hallucination_log import HallucinationLog
from app.hallucination.validator import hallucination_validator
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/hallucination", tags=["hallucination"])


class ValidateRequest(BaseModel):
    query: str
    response: str
    context: list[str] = []


@router.post("/validate")
async def validate_response(
    req: ValidateRequest,
    current_user: User = Depends(get_current_user),
):
    """Validate a response for hallucinations."""
    result = await hallucination_validator.validate(
        query=req.query,
        response=req.response,
        context=req.context,
    )
    return result


@router.get("/logs")
async def get_hallucination_logs(
    limit: int = Query(50, ge=1, le=200),
    risk_level: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get hallucination detection logs."""
    if not current_user.organization_id:
        raise HTTPException(status_code=400, detail="User must belong to an organization")

    query = db.query(HallucinationLog).filter(
        HallucinationLog.organization_id == current_user.organization_id
    )
    if risk_level:
        query = query.filter(HallucinationLog.risk_level == risk_level)

    logs = query.order_by(HallucinationLog.created_at.desc()).limit(limit).all()

    return [
        {
            "id": str(log.id),
            "confidence_score": float(log.confidence_score),
            "risk_level": log.risk_level,
            "detection_method": log.detection_method,
            "action_taken": log.action_taken,
            "is_resolved": log.is_resolved,
            "created_at": log.created_at.isoformat(),
        }
        for log in logs
    ]


@router.get("/stats")
async def get_hallucination_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get hallucination detection statistics."""
    if not current_user.organization_id:
        raise HTTPException(status_code=400, detail="User must belong to an organization")

    org_id = current_user.organization_id

    total = db.query(func.count(HallucinationLog.id)).filter(
        HallucinationLog.organization_id == org_id
    ).scalar() or 0

    by_level = db.query(
        HallucinationLog.risk_level,
        func.count(HallucinationLog.id).label("count"),
        func.avg(HallucinationLog.confidence_score).label("avg_score"),
    ).filter(
        HallucinationLog.organization_id == org_id
    ).group_by(HallucinationLog.risk_level).all()

    return {
        "total_checked": total,
        "by_risk_level": {
            r.risk_level: {"count": r.count, "avg_score": round(float(r.avg_score or 0), 2)}
            for r in by_level
        },
    }
