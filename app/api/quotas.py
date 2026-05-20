"""Quotas API — quota status, events, and admin reset."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.dependencies import get_current_user, get_current_superuser
from app.models.user import User
from app.models.usage_meter import QuotaEvent
from app.quota.enforcer import quota_enforcer
from app.tenancy.context import tenant_resolver
from app.utils.time_utils import current_month
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/quotas", tags=["quotas"])


@router.get("/status")
async def get_quota_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get current quota status for all quota types."""
    if not current_user.organization_id:
        raise HTTPException(status_code=400, detail="User must belong to an organization")

    org_id = str(current_user.organization_id)
    tenant = tenant_resolver.resolve(org_id, db)
    limits = tenant.limits

    usage = await quota_enforcer.get_all_usage(org_id)

    def build(quota_type: str, limit: float):
        current = usage.get(quota_type, 0.0)
        pct = round((current / limit) * 100, 1) if limit > 0 else 0.0
        return {
            "current": current,
            "limit": limit,
            "pct_used": pct,
            "is_soft_limit": pct >= limits.soft_limit_pct * 100,
            "is_hard_limit": current >= limit,
            "remaining": max(0.0, limit - current),
        }

    return {
        "period": current_month(),
        "plan": tenant.plan_name,
        "quotas": {
            "conversations": build("conversations", limits.max_conversations_per_month),
            "tokens": build("tokens", limits.max_tokens_per_month),
            "api_calls": build("api_calls", limits.max_api_calls_per_day * 30),
            "voice_minutes": build("voice", limits.max_voice_minutes_per_month),
            "agents": build("agents", limits.max_agents),
        },
    }


@router.get("/events")
async def get_quota_events(
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get recent quota enforcement events."""
    if not current_user.organization_id:
        raise HTTPException(status_code=400, detail="User must belong to an organization")

    events = (
        db.query(QuotaEvent)
        .filter(QuotaEvent.organization_id == current_user.organization_id)
        .order_by(QuotaEvent.created_at.desc())
        .limit(limit)
        .all()
    )

    return [
        {
            "id": str(e.id),
            "quota_type": e.quota_type,
            "event_type": e.event_type,
            "current_value": float(e.current_value),
            "limit_value": float(e.limit_value),
            "percentage_used": float(e.percentage_used),
            "message": e.message,
            "created_at": e.created_at.isoformat(),
        }
        for e in events
    ]


@router.post("/reset/{quota_type}")
async def reset_quota(
    quota_type: str,
    organization_id: str,
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db),
):
    """Admin: reset a quota counter for an organization (superuser only)."""
    period = current_month()
    key = f"quota:{organization_id}:{quota_type}:{period}"
    try:
        await quota_enforcer._increment.__func__(quota_enforcer, organization_id, quota_type, period, 0)
        from app.core.redis_client import redis_client
        await redis_client.delete(key)
        return {"message": f"Quota '{quota_type}' reset for org {organization_id}"}
    except Exception as e:
        logger.error(f"Quota reset error: {e}")
        raise HTTPException(status_code=500, detail="Failed to reset quota")
