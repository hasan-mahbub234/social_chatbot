"""Tenant context — resolves organization subscription and plan for a request."""
from dataclasses import dataclass
from typing import Optional
from sqlalchemy.orm import Session
from app.models.organization import Organization
from app.models.subscription import Subscription, SubscriptionPlan
from app.plans.definitions import get_plan, Plan
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class TenantContext:
    organization_id: str
    organization_name: str
    plan_name: str
    plan: Plan
    subscription_status: str          # active, past_due, trialing, canceled
    stripe_customer_id: Optional[str]
    stripe_subscription_id: Optional[str]
    is_active: bool

    @property
    def is_billable(self) -> bool:
        return self.subscription_status in ("active", "trialing")

    @property
    def features(self):
        return self.plan.features

    @property
    def limits(self):
        return self.plan.limits


class TenantResolver:
    """Resolve tenant context from organization_id."""

    def resolve(self, organization_id: str, db: Session) -> TenantContext:
        """Load org + subscription + plan and return TenantContext."""
        org = db.query(Organization).filter(
            Organization.id == organization_id,
            Organization.is_active == True,
        ).first()

        if not org:
            raise ValueError(f"Organization {organization_id} not found or inactive")

        subscription = db.query(Subscription).filter(
            Subscription.organization_id == organization_id,
        ).first()

        if subscription:
            plan_record = db.query(SubscriptionPlan).filter(
                SubscriptionPlan.id == subscription.plan_id,
            ).first()
            plan_name = plan_record.name if plan_record else "starter"
            status = subscription.status
            stripe_customer_id = subscription.stripe_customer_id
            stripe_subscription_id = subscription.stripe_subscription_id
        else:
            # No subscription → default to starter (free trial / no billing)
            plan_name = "starter"
            status = "active"
            stripe_customer_id = None
            stripe_subscription_id = None

        plan = get_plan(plan_name)

        return TenantContext(
            organization_id=str(organization_id),
            organization_name=org.name,
            plan_name=plan_name,
            plan=plan,
            subscription_status=status,
            stripe_customer_id=stripe_customer_id,
            stripe_subscription_id=stripe_subscription_id,
            is_active=org.is_active,
        )


tenant_resolver = TenantResolver()
