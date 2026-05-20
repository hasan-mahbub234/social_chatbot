"""Analytics API — per-org usage analytics and SaaS dashboard."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional
from app.core.database import get_db
from app.core.dependencies import get_current_user, get_current_superuser
from app.models.user import User
from app.models.usage_meter import UsageMeter, TenantUsage
from app.models.conversation import Conversation
from app.models.message import Message
from app.tenancy.context import tenant_resolver
from app.utils.time_utils import current_month
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/overview")
async def get_analytics_overview(
    period: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get analytics overview for the organization."""
    if not current_user.organization_id:
        raise HTTPException(status_code=400, detail="User must belong to an organization")

    org_id = current_user.organization_id
    period = period or current_month()

    meter = db.query(UsageMeter).filter(
        UsageMeter.organization_id == org_id,
        UsageMeter.period == period,
    ).first()

    total_conversations = db.query(func.count(Conversation.id)).filter(
        Conversation.agent_id.in_(
            db.query(Conversation.agent_id).filter(
                Conversation.user_id == current_user.id
            )
        )
    ).scalar() or 0

    total_messages = db.query(func.count(Message.id)).join(Conversation).filter(
        Conversation.user_id == current_user.id
    ).scalar() or 0

    return {
        "period": period,
        "conversations": {
            "total": total_conversations,
            "this_period": meter.conversations_count if meter else 0,
        },
        "messages": {
            "total": total_messages,
        },
        "tokens": {
            "total": int(meter.total_tokens) if meter else 0,
            "gpt4o": int(meter.gpt4o_tokens) if meter else 0,
            "gpt4o_mini": int(meter.gpt4o_mini_tokens) if meter else 0,
            "embeddings": int(meter.embedding_tokens) if meter else 0,
        },
        "cost": {
            "total_usd": float(meter.total_cost_usd or 0) if meter else 0.0,
            "gpt4o_usd": float(meter.gpt4o_cost_usd or 0) if meter else 0.0,
            "gpt4o_mini_usd": float(meter.gpt4o_mini_cost_usd or 0) if meter else 0.0,
        },
        "voice_minutes": float(meter.voice_minutes or 0) if meter else 0.0,
        "api_calls": meter.api_calls if meter else 0,
        "cache_hits": db.query(func.count(TenantUsage.id)).filter(
            TenantUsage.organization_id == org_id,
            TenantUsage.period == period,
            TenantUsage.from_cache == True,
        ).scalar() or 0,
    }


@router.get("/models")
async def get_model_usage(
    period: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get per-model usage breakdown."""
    if not current_user.organization_id:
        raise HTTPException(status_code=400, detail="User must belong to an organization")

    period = period or current_month()

    rows = db.query(
        TenantUsage.model,
        func.count(TenantUsage.id).label("calls"),
        func.sum(TenantUsage.total_tokens).label("tokens"),
        func.sum(TenantUsage.cost_usd).label("cost"),
    ).filter(
        TenantUsage.organization_id == current_user.organization_id,
        TenantUsage.period == period,
        TenantUsage.model.isnot(None),
    ).group_by(TenantUsage.model).all()

    return [
        {
            "model": r.model,
            "calls": r.calls,
            "tokens": int(r.tokens or 0),
            "cost_usd": float(r.cost or 0),
        }
        for r in rows
    ]


@router.get("/conversations/daily")
async def get_daily_conversations(
    days: int = Query(30, ge=1, le=90),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get daily conversation counts for the last N days."""
    if not current_user.organization_id:
        raise HTTPException(status_code=400, detail="User must belong to an organization")

    from datetime import datetime, timedelta
    rows = db.query(
        func.date(TenantUsage.created_at).label("date"),
        func.count(TenantUsage.id).label("count"),
    ).filter(
        TenantUsage.organization_id == current_user.organization_id,
        TenantUsage.usage_type == "chat",
        TenantUsage.created_at >= datetime.utcnow() - timedelta(days=days),
    ).group_by(func.date(TenantUsage.created_at)).order_by("date").all()

    return [{"date": str(r.date), "count": r.count} for r in rows]


@router.get("/saas", dependencies=[Depends(get_current_superuser)])
async def get_saas_analytics(db: Session = Depends(get_db)):
    """SaaS-level analytics — MRR, tenants, token spend (superuser only)."""
    from app.billing.analytics import saas_analytics
    return saas_analytics.get_overview(db)
