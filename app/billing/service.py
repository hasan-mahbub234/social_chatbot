"""Stripe billing service — subscription lifecycle management."""
import stripe
from typing import Optional, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.subscription import Subscription, SubscriptionPlan, Invoice, Payment
from app.models.organization import Organization
from app.core.logging import get_logger

logger = get_logger(__name__)

stripe.api_key = settings.STRIPE_SECRET_KEY


class BillingService:
    """Manage Stripe subscription lifecycle."""

    # ── Customer ──────────────────────────────────────────────────────────────

    async def get_or_create_customer(
        self,
        organization_id: str,
        email: str,
        name: str,
        db: Session,
    ) -> str:
        """Get existing Stripe customer or create a new one."""
        subscription = db.query(Subscription).filter(
            Subscription.organization_id == organization_id,
        ).first()

        if subscription and subscription.stripe_customer_id:
            return subscription.stripe_customer_id

        customer = stripe.Customer.create(
            email=email,
            name=name,
            metadata={"organization_id": organization_id},
        )
        logger.info("stripe_customer_created", customer_id=customer.id, org=organization_id)
        return customer.id

    # ── Checkout ──────────────────────────────────────────────────────────────

    async def create_checkout_session(
        self,
        organization_id: str,
        plan_name: str,
        billing_cycle: str,
        success_url: str,
        cancel_url: str,
        customer_email: str,
        db: Session,
    ) -> Dict[str, Any]:
        """Create a Stripe Checkout session for a new subscription."""
        plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.name == plan_name).first()
        if not plan:
            raise ValueError(f"Plan '{plan_name}' not found")

        price_id = (
            plan.stripe_price_id_yearly
            if billing_cycle == "yearly"
            else plan.stripe_price_id_monthly
        )
        if not price_id:
            raise ValueError(f"Stripe price not configured for plan '{plan_name}' ({billing_cycle})")

        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            mode="subscription",
            customer_email=customer_email,
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={
                "organization_id": organization_id,
                "plan_name": plan_name,
                "billing_cycle": billing_cycle,
            },
            subscription_data={
                "metadata": {
                    "organization_id": organization_id,
                    "plan_name": plan_name,
                }
            },
        )

        logger.info("checkout_session_created", org=organization_id, plan=plan_name)
        return {"checkout_url": session.url, "session_id": session.id}

    # ── Upgrade / Downgrade ───────────────────────────────────────────────────

    async def change_plan(
        self,
        organization_id: str,
        new_plan_name: str,
        billing_cycle: str,
        db: Session,
    ) -> Subscription:
        """Upgrade or downgrade subscription plan."""
        subscription = db.query(Subscription).filter(
            Subscription.organization_id == organization_id,
        ).first()

        if not subscription or not subscription.stripe_subscription_id:
            raise ValueError("No active Stripe subscription found")

        new_plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.name == new_plan_name).first()
        if not new_plan:
            raise ValueError(f"Plan '{new_plan_name}' not found")

        price_id = (
            new_plan.stripe_price_id_yearly
            if billing_cycle == "yearly"
            else new_plan.stripe_price_id_monthly
        )

        # Retrieve current Stripe subscription to get item ID
        stripe_sub = stripe.Subscription.retrieve(subscription.stripe_subscription_id)
        item_id = stripe_sub["items"]["data"][0]["id"]

        # Modify subscription
        stripe.Subscription.modify(
            subscription.stripe_subscription_id,
            items=[{"id": item_id, "price": price_id}],
            proration_behavior="create_prorations",
            metadata={"plan_name": new_plan_name},
        )

        # Update local record
        subscription.plan_id = new_plan.id
        subscription.billing_cycle = billing_cycle
        db.commit()
        db.refresh(subscription)

        logger.info("plan_changed", org=organization_id, new_plan=new_plan_name)
        return subscription

    # ── Cancel ────────────────────────────────────────────────────────────────

    async def cancel_subscription(
        self,
        organization_id: str,
        at_period_end: bool,
        db: Session,
    ) -> Subscription:
        """Cancel subscription immediately or at period end."""
        subscription = db.query(Subscription).filter(
            Subscription.organization_id == organization_id,
        ).first()

        if not subscription or not subscription.stripe_subscription_id:
            raise ValueError("No active subscription found")

        if at_period_end:
            stripe.Subscription.modify(
                subscription.stripe_subscription_id,
                cancel_at_period_end=True,
            )
            subscription.cancel_at_period_end = True
        else:
            stripe.Subscription.cancel(subscription.stripe_subscription_id)
            subscription.status = "canceled"
            subscription.canceled_at = datetime.utcnow()

        db.commit()
        db.refresh(subscription)
        logger.info("subscription_canceled", org=organization_id, at_period_end=at_period_end)
        return subscription

    # ── Invoices ──────────────────────────────────────────────────────────────

    async def list_invoices(
        self,
        organization_id: str,
        db: Session,
        limit: int = 10,
    ) -> list:
        """List invoices for an organization."""
        return (
            db.query(Invoice)
            .filter(Invoice.organization_id == organization_id)
            .order_by(Invoice.created_at.desc())
            .limit(limit)
            .all()
        )

    async def get_upcoming_invoice(self, organization_id: str, db: Session) -> Optional[Dict]:
        """Get upcoming invoice from Stripe."""
        subscription = db.query(Subscription).filter(
            Subscription.organization_id == organization_id,
        ).first()

        if not subscription or not subscription.stripe_customer_id:
            return None

        try:
            invoice = stripe.Invoice.upcoming(customer=subscription.stripe_customer_id)
            return {
                "amount_due": invoice.amount_due / 100,
                "currency": invoice.currency,
                "period_start": datetime.fromtimestamp(invoice.period_start).isoformat(),
                "period_end": datetime.fromtimestamp(invoice.period_end).isoformat(),
                "next_payment_attempt": (
                    datetime.fromtimestamp(invoice.next_payment_attempt).isoformat()
                    if invoice.next_payment_attempt else None
                ),
            }
        except stripe.error.InvalidRequestError:
            return None

    # ── Portal ────────────────────────────────────────────────────────────────

    async def create_portal_session(
        self,
        organization_id: str,
        return_url: str,
        db: Session,
    ) -> str:
        """Create Stripe Customer Portal session for self-service billing."""
        subscription = db.query(Subscription).filter(
            Subscription.organization_id == organization_id,
        ).first()

        if not subscription or not subscription.stripe_customer_id:
            raise ValueError("No Stripe customer found")

        session = stripe.billing_portal.Session.create(
            customer=subscription.stripe_customer_id,
            return_url=return_url,
        )
        return session.url

    # ── Payment method ────────────────────────────────────────────────────────

    async def get_payment_methods(self, organization_id: str, db: Session) -> list:
        """List saved payment methods for a customer."""
        subscription = db.query(Subscription).filter(
            Subscription.organization_id == organization_id,
        ).first()

        if not subscription or not subscription.stripe_customer_id:
            return []

        methods = stripe.PaymentMethod.list(
            customer=subscription.stripe_customer_id,
            type="card",
        )
        return [
            {
                "id": pm.id,
                "brand": pm.card.brand,
                "last4": pm.card.last4,
                "exp_month": pm.card.exp_month,
                "exp_year": pm.card.exp_year,
            }
            for pm in methods.data
        ]


billing_service = BillingService()
