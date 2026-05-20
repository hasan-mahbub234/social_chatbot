"""Tenant dependency — FastAPI dependency for resolving TenantContext in routes."""
from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.tenancy.context import TenantContext, tenant_resolver
from app.core.logging import get_logger

logger = get_logger(__name__)


async def get_tenant(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TenantContext:
    """Resolve TenantContext for the current user's organization."""
    if not current_user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User must belong to an organization to access this resource.",
        )
    try:
        return tenant_resolver.resolve(str(current_user.organization_id), db)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


async def require_active_subscription(
    tenant: TenantContext = Depends(get_tenant),
) -> TenantContext:
    """Require an active (non-canceled, non-past_due) subscription."""
    if not tenant.is_billable:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "code": "SUBSCRIPTION_INACTIVE",
                "message": "Your subscription is inactive. Please update your billing.",
                "status": tenant.subscription_status,
            },
        )
    return tenant
