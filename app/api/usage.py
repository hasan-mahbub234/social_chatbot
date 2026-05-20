"""Usage API — current usage, history, per-agent breakdown."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.usage_meter import UsageMeter, TenantUsage
from app.quota.enforcer import quota_enforcer
from app.tenancy.context import tenant_resolver
from app.utils.time_utils import current_month
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/usage", tags=["usage"])


@router.get("/current")
async def get_current_usage(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get current billing period usage and quota status."""
    if not current_user.organization_id:
        raise HTTPException(status_code=400, detail="User must belong to an organization")

    org_id = str(current_user.organization_id)
    period = current_month()
    tenant = tenant_resolver.resolve(org_id, db)
    limits = tenant.limits

    meter = db.query(UsageMeter).filter(
        UsageMeter.organization_id == current_user.organization_id,
        UsageMeter.period == period,
    ).first()

    conversations = meter.conversations_count if meter else 0
    tokens = int(meter.total_tokens) if meter else 0
    api_calls = meter.api_calls if meter else 0
    voice_minutes = float(meter.voice_minutes or 0) if meter else 0.0
    total_cost = float(meter.total_cost_usd or 0) if meter else 0.0

    def pct(current, limit):
        return round((current / limit) * 100, 1) if limit > 0 else 0.0

    return {
        "period": period,
        "plan": tenant.plan_name,
        "usage": {
            "conversations": {
                "used": conversations,
                "limit": limits.max_conversations_per_month,
                "pct": pct(conversations, limits.max_conversations_per_month),
            },
            "tokens": {
                "used": tokens,
                "limit": limits.max_tokens_per_month,
                "pct": pct(tokens, limits.max_tokens_per_month),
                "gpt4o_tokens": int(meter.gpt4o_tokens) if meter else 0,
                "gpt4o_mini_tokens": int(meter.gpt4o_mini_tokens) if meter else 0,
                "embedding_tokens": int(meter.embedding_tokens) if meter else 0,
            },
            "api_calls": {
                "used": api_calls,
                "limit": limits.max_api_calls_per_day * 30,
                "pct": pct(api_calls, limits.max_api_calls_per_day * 30),
            },
            "voice_minutes": {
                "used": voice_minutes,
                "limit": limits.max_voice_minutes_per_month,
                "pct": pct(voice_minutes, limits.max_voice_minutes_per_month),
            },
        },
        "cost": {
            "total_usd": total_cost,
            "gpt4o_usd": float(meter.gpt4o_cost_usd or 0) if meter else 0.0,
            "gpt4o_mini_usd": float(meter.gpt4o_mini_cost_usd or 0) if meter else 0.0,
            "embedding_usd": float(meter.embedding_cost_usd or 0) if meter else 0.0,
            "voice_usd": float(meter.voice_cost_usd or 0) if meter else 0.0,
        },
    }


@router.get("/history")
async def get_usage_history(
    months: int = Query(6, ge=1, le=24),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get usage history for the last N months."""
    if not current_user.organization_id:
        raise HTTPException(status_code=400, detail="User must belong to an organization")

    meters = (
        db.query(UsageMeter)
        .filter(UsageMeter.organization_id == current_user.organization_id)
        .order_by(UsageMeter.period.desc())
        .limit(months)
        .all()
    )

    return [
        {
            "period": m.period,
            "conversations": m.conversations_count,
            "total_tokens": int(m.total_tokens),
            "gpt4o_tokens": int(m.gpt4o_tokens),
            "gpt4o_mini_tokens": int(m.gpt4o_mini_tokens),
            "api_calls": m.api_calls,
            "voice_minutes": float(m.voice_minutes or 0),
            "total_cost_usd": float(m.total_cost_usd or 0),
        }
        for m in meters
    ]


@router.get("/events")
async def get_usage_events(
    limit: int = Query(50, ge=1, le=200),
    usage_type: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get granular usage events for the current period."""
    if not current_user.organization_id:
        raise HTTPException(status_code=400, detail="User must belong to an organization")

    period = current_month()
    query = db.query(TenantUsage).filter(
        TenantUsage.organization_id == current_user.organization_id,
        TenantUsage.period == period,
    )
    if usage_type:
        query = query.filter(TenantUsage.usage_type == usage_type)

    events = query.order_by(TenantUsage.created_at.desc()).limit(limit).all()

    return [
        {
            "id": str(e.id),
            "usage_type": e.usage_type,
            "model": e.model,
            "total_tokens": e.total_tokens,
            "cost_usd": float(e.cost_usd or 0),
            "from_cache": e.from_cache,
            "duration_ms": e.duration_ms,
            "created_at": e.created_at.isoformat(),
        }
        for e in events
    ]
