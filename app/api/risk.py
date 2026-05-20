"""Risk API — risk assessment logs and scoring."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional
from pydantic import BaseModel
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.risk_assessment import RiskAssessment
from app.risk.risk_engine import risk_engine
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/risk", tags=["risk"])


class ScoreRequest(BaseModel):
    text: str


@router.post("/score")
async def score_text(
    req: ScoreRequest,
    current_user: User = Depends(get_current_user),
):
    """Score text for risk."""
    result = await risk_engine.score(
        text=req.text,
        user_id=str(current_user.id),
        organization_id=str(current_user.organization_id) if current_user.organization_id else "",
    )
    return result


@router.get("/assessments")
async def get_risk_assessments(
    limit: int = Query(50, ge=1, le=200),
    risk_level: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get risk assessment records."""
    if not current_user.organization_id:
        raise HTTPException(status_code=400, detail="User must belong to an organization")

    query = db.query(RiskAssessment).filter(
        RiskAssessment.organization_id == current_user.organization_id
    )
    if risk_level:
        query = query.filter(RiskAssessment.risk_level == risk_level)

    records = query.order_by(RiskAssessment.created_at.desc()).limit(limit).all()

    return [
        {
            "id": str(r.id),
            "assessment_type": r.assessment_type,
            "risk_level": r.risk_level,
            "risk_score": float(r.risk_score),
            "is_escalated": r.is_escalated,
            "created_at": r.created_at.isoformat(),
        }
        for r in records
    ]


@router.get("/stats")
async def get_risk_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get risk assessment statistics."""
    if not current_user.organization_id:
        raise HTTPException(status_code=400, detail="User must belong to an organization")

    org_id = current_user.organization_id

    by_level = db.query(
        RiskAssessment.risk_level,
        func.count(RiskAssessment.id).label("count"),
        func.avg(RiskAssessment.risk_score).label("avg_score"),
    ).filter(
        RiskAssessment.organization_id == org_id
    ).group_by(RiskAssessment.risk_level).all()

    escalated = db.query(func.count(RiskAssessment.id)).filter(
        RiskAssessment.organization_id == org_id,
        RiskAssessment.is_escalated == True,
    ).scalar() or 0

    return {
        "by_risk_level": {
            r.risk_level: {"count": r.count, "avg_score": round(float(r.avg_score or 0), 2)}
            for r in by_level
        },
        "escalated_count": escalated,
    }
