"""Stripe webhook event processor."""
import stripe
from datetime import datetime
from typing import Dict, Any
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.subscription import Subscription, SubscriptionPlan, Invoice, Payment
from app.core.logging import get_logger

logger = get_logger(__name__)


class StripeWebhookHandler:
    """Process Stripe webhook events and sync local DB state."""

    def verify_signature(self, payload: bytes, sig_header: str) -> Dict[str, Any]:
        """Verify Stripe webhook signature and return parsed event."""
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
            )
            return event
        except stripe.error.SignatureVerificationError as e:
            logger.error("stripe_webhook_signature_invalid", error=str(e))
            raise ValueError("Invalid webhook signature")

    async def handle(self, event: Dict[str, Any], db: Session) -> Dict[str, str]:
        """Route event to appropriate handler."""
        event_type = event["type"]
        data = event["data"]["object"]

        handlers = {
            "checkout.session.completed": self._on_checkout_completed,
            "customer.subscription.created": self._on_subscription_created,
            "customer.subscription.updated": self._on_subscription_updated,
            "customer.subscription.deleted": self._on_subscription_deleted,
            "invoice.paid": self._on_invoice_paid,
            "invoice.payment_failed": self._on_invoice_payment_failed,
            "invoice.created": self._on_invoice_created,
            "payment_intent.succeeded": self._on_payment_succeeded,
            "payment_intent.payment_failed": self._on_payment_failed,
        }

        handler = handlers.get(event_type)
        if handler:
            await handler(data, db)
            logger.info("stripe_webhook_handled", event_type=event_type)
        else:
            logger.info("stripe_webhook_unhandled", event_type=event_type)

        return {"status": "ok", "event_type": event_type}

    # ── Checkout ──────────────────────────────────────────────────────────────

    async def _on_checkout_completed(self, data: Dict, db: Session):
        """Provision subscription after successful checkout."""
        if data.get("mode") != "subscription":
            return

        org_id = data.get("metadata", {}).get("organization_id")
        plan_name = data.get("metadata", {}).get("plan_name", "starter")
        billing_cycle = data.get("metadata", {}).get("billing_cycle", "monthly")
        stripe_customer_id = data.get("customer")
        stripe_subscription_id = data.get("subscription")

        if not org_id:
            logger.error("checkout_missing_org_id")
            return

        plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.name == plan_name).first()
        if not plan:
            logger.error("checkout_plan_not_found", plan=plan_name)
            return

        existing = db.query(Subscription).filter(
            Subscription.organization_id == org_id,
        ).first()

        if existing:
            existing.plan_id = plan.id
            existing.stripe_customer_id = stripe_customer_id
            existing.stripe_subscription_id = stripe_subscription_id
            existing.status = "active"
            existing.billing_cycle = billing_cycle
        else:
            sub = Subscription(
                organization_id=org_id,
                plan_id=plan.id,
                stripe_customer_id=stripe_customer_id,
                stripe_subscription_id=stripe_subscription_id,
                status="active",
                billing_cycle=billing_cycle,
            )
            db.add(sub)

        db.commit()
        logger.info("subscription_provisioned", org=org_id, plan=plan_name)

    # ── Subscription events ───────────────────────────────────────────────────

    async def _on_subscription_created(self, data: Dict, db: Session):
        org_id = data.get("metadata", {}).get("organization_id")
        if not org_id:
            return
        await self._sync_subscription(data, db, org_id)

    async def _on_subscription_updated(self, data: Dict, db: Session):
        stripe_sub_id = data.get("id")
        sub = db.query(Subscription).filter(
            Subscription.stripe_subscription_id == stripe_sub_id,
        ).first()
        if not sub:
            return

        sub.status = data.get("status", sub.status)
        sub.cancel_at_period_end = data.get("cancel_at_period_end", False)

        period_start = data.get("current_period_start")
        period_end = data.get("current_period_end")
        if period_start:
            sub.current_period_start = datetime.fromtimestamp(period_start)
        if period_end:
            sub.current_period_end = datetime.fromtimestamp(period_end)

        # Sync plan if changed
        items = data.get("items", {}).get("data", [])
        if items:
            price_id = items[0].get("price", {}).get("id")
            if price_id:
                plan = db.query(SubscriptionPlan).filter(
                    (SubscriptionPlan.stripe_price_id_monthly == price_id) |
                    (SubscriptionPlan.stripe_price_id_yearly == price_id)
                ).first()
                if plan:
                    sub.plan_id = plan.id

        db.commit()
        logger.info("subscription_synced", stripe_sub_id=stripe_sub_id, status=sub.status)

    async def _on_subscription_deleted(self, data: Dict, db: Session):
        stripe_sub_id = data.get("id")
        sub = db.query(Subscription).filter(
            Subscription.stripe_subscription_id == stripe_sub_id,
        ).first()
        if sub:
            sub.status = "canceled"
            sub.canceled_at = datetime.utcnow()
            db.commit()
            logger.info("subscription_canceled_webhook", stripe_sub_id=stripe_sub_id)

    # ── Invoice events ────────────────────────────────────────────────────────

    async def _on_invoice_created(self, data: Dict, db: Session):
        await self._upsert_invoice(data, db)

    async def _on_invoice_paid(self, data: Dict, db: Session):
        invoice = await self._upsert_invoice(data, db)
        if invoice:
            invoice.status = "paid"
            invoice.paid_at = datetime.utcnow()
            db.commit()

        # Reactivate subscription if it was past_due
        stripe_sub_id = data.get("subscription")
        if stripe_sub_id:
            sub = db.query(Subscription).filter(
                Subscription.stripe_subscription_id == stripe_sub_id,
            ).first()
            if sub and sub.status == "past_due":
                sub.status = "active"
                db.commit()
                logger.info("subscription_reactivated", stripe_sub_id=stripe_sub_id)

    async def _on_invoice_payment_failed(self, data: Dict, db: Session):
        await self._upsert_invoice(data, db)

        stripe_sub_id = data.get("subscription")
        if stripe_sub_id:
            sub = db.query(Subscription).filter(
                Subscription.stripe_subscription_id == stripe_sub_id,
            ).first()
            if sub:
                sub.status = "past_due"
                db.commit()
                logger.warning("subscription_past_due", stripe_sub_id=stripe_sub_id)

    # ── Payment events ────────────────────────────────────────────────────────

    async def _on_payment_succeeded(self, data: Dict, db: Session):
        self._upsert_payment(data, "succeeded", db)

    async def _on_payment_failed(self, data: Dict, db: Session):
        self._upsert_payment(data, "failed", db)

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _upsert_invoice(self, data: Dict, db: Session):
        stripe_invoice_id = data.get("id")
        if not stripe_invoice_id:
            return None

        existing = db.query(Invoice).filter(
            Invoice.stripe_invoice_id == stripe_invoice_id,
        ).first()

        # Resolve org from customer
        stripe_customer_id = data.get("customer")
        sub = db.query(Subscription).filter(
            Subscription.stripe_customer_id == stripe_customer_id,
        ).first()
        if not sub:
            return None

        if existing:
            existing.status = data.get("status", existing.status)
            existing.amount_paid = (data.get("amount_paid") or 0) / 100
            db.commit()
            return existing

        invoice = Invoice(
            organization_id=sub.organization_id,
            subscription_id=sub.id,
            stripe_invoice_id=stripe_invoice_id,
            stripe_payment_intent_id=data.get("payment_intent"),
            amount_due=(data.get("amount_due") or 0) / 100,
            amount_paid=(data.get("amount_paid") or 0) / 100,
            currency=data.get("currency", "usd"),
            status=data.get("status", "open"),
            invoice_pdf=data.get("invoice_pdf"),
            hosted_invoice_url=data.get("hosted_invoice_url"),
            period_start=datetime.fromtimestamp(data["period_start"]) if data.get("period_start") else None,
            period_end=datetime.fromtimestamp(data["period_end"]) if data.get("period_end") else None,
        )
        db.add(invoice)
        db.commit()
        return invoice

    def _upsert_payment(self, data: Dict, status: str, db: Session):
        pi_id = data.get("id")
        if not pi_id:
            return

        existing = db.query(Payment).filter(
            Payment.stripe_payment_intent_id == pi_id,
        ).first()

        if existing:
            existing.status = status
            db.commit()
            return

        # Resolve org
        stripe_customer_id = data.get("customer")
        sub = db.query(Subscription).filter(
            Subscription.stripe_customer_id == stripe_customer_id,
        ).first()
        if not sub:
            return

        payment = Payment(
            organization_id=sub.organization_id,
            stripe_payment_intent_id=pi_id,
            stripe_charge_id=data.get("latest_charge"),
            amount=(data.get("amount") or 0) / 100,
            currency=data.get("currency", "usd"),
            status=status,
            failure_code=data.get("last_payment_error", {}).get("code") if status == "failed" else None,
            failure_message=data.get("last_payment_error", {}).get("message") if status == "failed" else None,
        )
        db.add(payment)
        db.commit()

    async def _sync_subscription(self, data: Dict, db: Session, org_id: str):
        plan_name = data.get("metadata", {}).get("plan_name", "starter")
        plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.name == plan_name).first()

        sub = db.query(Subscription).filter(
            Subscription.organization_id == org_id,
        ).first()

        period_start = data.get("current_period_start")
        period_end = data.get("current_period_end")

        if sub:
            sub.stripe_subscription_id = data.get("id")
            sub.stripe_customer_id = data.get("customer")
            sub.status = data.get("status", "active")
            if plan:
                sub.plan_id = plan.id
            if period_start:
                sub.current_period_start = datetime.fromtimestamp(period_start)
            if period_end:
                sub.current_period_end = datetime.fromtimestamp(period_end)
        else:
            if not plan:
                return
            sub = Subscription(
                organization_id=org_id,
                plan_id=plan.id,
                stripe_subscription_id=data.get("id"),
                stripe_customer_id=data.get("customer"),
                status=data.get("status", "active"),
                current_period_start=datetime.fromtimestamp(period_start) if period_start else None,
                current_period_end=datetime.fromtimestamp(period_end) if period_end else None,
            )
            db.add(sub)

        db.commit()


stripe_webhook_handler = StripeWebhookHandler()
