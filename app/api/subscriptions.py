"""Subscriptions API — checkout, upgrade, downgrade, cancel, portal."""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.subscription import Subscription, SubscriptionPlan
from app.billing.service import billing_service
from app.tenancy.context import tenant_resolver
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


class CheckoutRequest(BaseModel):
    plan_name: str
    billing_cycle: str = "monthly"


class ChangePlanRequest(BaseModel):
    new_plan_name: str
    billing_cycle: str = "monthly"


class CancelRequest(BaseModel):
    at_period_end: bool = True


@router.post("/checkout")
async def create_checkout(
    req: CheckoutRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a Stripe Checkout session to subscribe to a plan."""
    if not current_user.organization_id:
        raise HTTPException(status_code=400, detail="User must belong to an organization")

    try:
        result = await billing_service.create_checkout_session(
            organization_id=str(current_user.organization_id),
            plan_name=req.plan_name,
            billing_cycle=req.billing_cycle,
            success_url=settings.BILLING_SUCCESS_URL,
            cancel_url=settings.BILLING_CANCEL_URL,
            customer_email=current_user.email,
            db=db,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Checkout error: {e}")
        raise HTTPException(status_code=500, detail="Failed to create checkout session")


@router.get("/current")
async def get_current_subscription(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get current subscription for the user's organization."""
    if not current_user.organization_id:
        raise HTTPException(status_code=400, detail="User must belong to an organization")

    tenant = tenant_resolver.resolve(str(current_user.organization_id), db)
    sub = db.query(Subscription).filter(
        Subscription.organization_id == current_user.organization_id,
    ).first()

    return {
        "plan_name": tenant.plan_name,
        "plan_display_name": tenant.plan.display_name,
        "status": tenant.subscription_status,
        "is_active": tenant.is_billable,
        "limits": {
            "max_conversations_per_month": tenant.limits.max_conversations_per_month,
            "max_tokens_per_month": tenant.limits.max_tokens_per_month,
            "max_agents": tenant.limits.max_agents,
            "max_api_calls_per_day": tenant.limits.max_api_calls_per_day,
            "max_storage_mb": tenant.limits.max_storage_mb,
            "max_voice_minutes_per_month": tenant.limits.max_voice_minutes_per_month,
            "rate_limit_per_minute": tenant.limits.rate_limit_per_minute,
        },
        "features": {
            "gpt4o_access": tenant.features.gpt4o_access,
            "voice_access": tenant.features.voice_access,
            "advanced_governance": tenant.features.advanced_governance,
            "audit_export": tenant.features.audit_export,
            "webhook_integrations": tenant.features.webhook_integrations,
            "analytics_dashboard": tenant.features.analytics_dashboard,
        },
        "stripe_subscription_id": sub.stripe_subscription_id if sub else None,
        "current_period_end": sub.current_period_end.isoformat() if sub and sub.current_period_end else None,
        "cancel_at_period_end": sub.cancel_at_period_end if sub else False,
    }


@router.post("/change-plan")
async def change_plan(
    req: ChangePlanRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upgrade or downgrade subscription plan."""
    if not current_user.organization_id:
        raise HTTPException(status_code=400, detail="User must belong to an organization")

    try:
        sub = await billing_service.change_plan(
            organization_id=str(current_user.organization_id),
            new_plan_name=req.new_plan_name,
            billing_cycle=req.billing_cycle,
            db=db,
        )
        return {"message": f"Plan changed to {req.new_plan_name}", "status": sub.status}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Plan change error: {e}")
        raise HTTPException(status_code=500, detail="Failed to change plan")


@router.post("/cancel")
async def cancel_subscription(
    req: CancelRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Cancel subscription."""
    if not current_user.organization_id:
        raise HTTPException(status_code=400, detail="User must belong to an organization")

    try:
        sub = await billing_service.cancel_subscription(
            organization_id=str(current_user.organization_id),
            at_period_end=req.at_period_end,
            db=db,
        )
        msg = "Subscription will cancel at period end" if req.at_period_end else "Subscription canceled immediately"
        return {"message": msg, "status": sub.status}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Cancel error: {e}")
        raise HTTPException(status_code=500, detail="Failed to cancel subscription")


@router.get("/portal")
async def billing_portal(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get Stripe Customer Portal URL for self-service billing management."""
    if not current_user.organization_id:
        raise HTTPException(status_code=400, detail="User must belong to an organization")

    try:
        url = await billing_service.create_portal_session(
            organization_id=str(current_user.organization_id),
            return_url=settings.BILLING_PORTAL_RETURN_URL,
            db=db,
        )
        return {"portal_url": url}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Portal error: {e}")
        raise HTTPException(status_code=500, detail="Failed to create portal session")


@router.get("/payment-methods")
async def get_payment_methods(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List saved payment methods."""
    if not current_user.organization_id:
        raise HTTPException(status_code=400, detail="User must belong to an organization")

    methods = await billing_service.get_payment_methods(
        organization_id=str(current_user.organization_id),
        db=db,
    )
    return {"payment_methods": methods}
