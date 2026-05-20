"""Subscription and billing models."""
from sqlalchemy import Column, String, DateTime, Boolean, Numeric, Integer, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from app.core.database import Base


class SubscriptionPlan(Base):
    """Subscription plan definition (Starter / Growth / Enterprise)."""

    __tablename__ = "subscription_plans"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(50), unique=True, nullable=False)          # starter, growth, enterprise
    display_name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)

    # Stripe
    stripe_product_id = Column(String(255), nullable=True)
    stripe_price_id_monthly = Column(String(255), nullable=True)
    stripe_price_id_yearly = Column(String(255), nullable=True)

    # Pricing
    price_monthly = Column(Numeric(10, 2), default=0.0)
    price_yearly = Column(Numeric(10, 2), default=0.0)

    # Limits
    max_conversations_per_month = Column(Integer, default=500)
    max_tokens_per_month = Column(Integer, default=1_000_000)
    max_agents = Column(Integer, default=3)
    max_api_calls_per_day = Column(Integer, default=1000)
    max_storage_mb = Column(Integer, default=500)
    max_voice_minutes_per_month = Column(Integer, default=0)
    max_team_members = Column(Integer, default=3)
    rate_limit_per_minute = Column(Integer, default=20)

    # Feature flags (stored as JSONB for flexibility)
    features = Column(JSONB, default={})

    is_active = Column(Boolean, default=True)
    is_public = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    subscriptions = relationship("Subscription", back_populates="plan")

    def __repr__(self):
        return f"<SubscriptionPlan {self.name}>"


class Subscription(Base):
    """Active subscription for an organization."""

    __tablename__ = "subscriptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, unique=True)
    plan_id = Column(UUID(as_uuid=True), ForeignKey("subscription_plans.id"), nullable=False)

    # Stripe
    stripe_customer_id = Column(String(255), nullable=True, index=True)
    stripe_subscription_id = Column(String(255), nullable=True, unique=True, index=True)

    # Status
    status = Column(String(50), default="active")   # active, past_due, canceled, trialing, paused
    billing_cycle = Column(String(20), default="monthly")  # monthly, yearly

    # Dates
    trial_ends_at = Column(DateTime, nullable=True)
    current_period_start = Column(DateTime, nullable=True)
    current_period_end = Column(DateTime, nullable=True)
    canceled_at = Column(DateTime, nullable=True)
    cancel_at_period_end = Column(Boolean, default=False)

    # Metadata
    extra_data = Column("extra_data", JSONB, default={})

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    plan = relationship("SubscriptionPlan", back_populates="subscriptions")
    organization = relationship("Organization", back_populates="subscription")
    invoices = relationship("Invoice", back_populates="subscription")

    def __repr__(self):
        return f"<Subscription org={self.organization_id} plan={self.plan_id} status={self.status}>"


class Invoice(Base):
    """Stripe invoice record."""

    __tablename__ = "invoices"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    subscription_id = Column(UUID(as_uuid=True), ForeignKey("subscriptions.id"), nullable=True)

    stripe_invoice_id = Column(String(255), unique=True, nullable=False, index=True)
    stripe_payment_intent_id = Column(String(255), nullable=True)

    amount_due = Column(Numeric(10, 2), nullable=False)
    amount_paid = Column(Numeric(10, 2), default=0.0)
    currency = Column(String(10), default="usd")

    status = Column(String(50), nullable=False)   # draft, open, paid, void, uncollectible
    invoice_pdf = Column(String(500), nullable=True)
    hosted_invoice_url = Column(String(500), nullable=True)

    period_start = Column(DateTime, nullable=True)
    period_end = Column(DateTime, nullable=True)
    due_date = Column(DateTime, nullable=True)
    paid_at = Column(DateTime, nullable=True)

    line_items = Column(JSONB, default=[])
    extra_data = Column("extra_data", JSONB, default={})

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    subscription = relationship("Subscription", back_populates="invoices")

    def __repr__(self):
        return f"<Invoice {self.stripe_invoice_id} status={self.status}>"


class Payment(Base):
    """Payment record."""

    __tablename__ = "payments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)

    stripe_payment_intent_id = Column(String(255), unique=True, nullable=False, index=True)
    stripe_charge_id = Column(String(255), nullable=True)

    amount = Column(Numeric(10, 2), nullable=False)
    currency = Column(String(10), default="usd")
    status = Column(String(50), nullable=False)   # succeeded, failed, pending, refunded

    failure_code = Column(String(100), nullable=True)
    failure_message = Column(Text, nullable=True)

    extra_data = Column("extra_data", JSONB, default={})
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<Payment {self.stripe_payment_intent_id} status={self.status}>"
