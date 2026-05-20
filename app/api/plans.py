"""Plans API — list available subscription plans."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.subscription import SubscriptionPlan
from app.core.dependencies import get_current_user
from app.models.user import User

router = APIRouter(prefix="/plans", tags=["plans"])


@router.get("/")
async def list_plans(db: Session = Depends(get_db)):
    """List all public subscription plans."""
    plans = (
        db.query(SubscriptionPlan)
        .filter(SubscriptionPlan.is_active == True, SubscriptionPlan.is_public == True)
        .order_by(SubscriptionPlan.sort_order)
        .all()
    )
    return [
        {
            "id": str(p.id),
            "name": p.name,
            "display_name": p.display_name,
            "description": p.description,
            "price_monthly": float(p.price_monthly),
            "price_yearly": float(p.price_yearly),
            "limits": {
                "max_conversations_per_month": p.max_conversations_per_month,
                "max_tokens_per_month": p.max_tokens_per_month,
                "max_agents": p.max_agents,
                "max_api_calls_per_day": p.max_api_calls_per_day,
                "max_storage_mb": p.max_storage_mb,
                "max_voice_minutes_per_month": p.max_voice_minutes_per_month,
                "max_team_members": p.max_team_members,
                "rate_limit_per_minute": p.rate_limit_per_minute,
            },
            "features": p.features,
        }
        for p in plans
    ]


@router.get("/{plan_name}")
async def get_plan(plan_name: str, db: Session = Depends(get_db)):
    """Get a specific plan by name."""
    plan = db.query(SubscriptionPlan).filter(
        SubscriptionPlan.name == plan_name,
        SubscriptionPlan.is_active == True,
    ).first()
    if not plan:
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")
    return {
        "id": str(plan.id),
        "name": plan.name,
        "display_name": plan.display_name,
        "description": plan.description,
        "price_monthly": float(plan.price_monthly),
        "price_yearly": float(plan.price_yearly),
        "limits": {
            "max_conversations_per_month": plan.max_conversations_per_month,
            "max_tokens_per_month": plan.max_tokens_per_month,
            "max_agents": plan.max_agents,
            "max_api_calls_per_day": plan.max_api_calls_per_day,
            "max_storage_mb": plan.max_storage_mb,
            "max_voice_minutes_per_month": plan.max_voice_minutes_per_month,
            "max_team_members": plan.max_team_members,
            "rate_limit_per_minute": plan.rate_limit_per_minute,
        },
        "features": plan.features,
    }
