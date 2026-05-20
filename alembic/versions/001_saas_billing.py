"""Add multi-tenant SaaS billing tables.

Revision ID: 001_saas_billing
Revises:
Create Date: 2024-01-01 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "001_saas_billing"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── subscription_plans ────────────────────────────────────────────────────
    op.create_table(
        "subscription_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(50), unique=True, nullable=False),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("stripe_product_id", sa.String(255), nullable=True),
        sa.Column("stripe_price_id_monthly", sa.String(255), nullable=True),
        sa.Column("stripe_price_id_yearly", sa.String(255), nullable=True),
        sa.Column("price_monthly", sa.Numeric(10, 2), default=0.0),
        sa.Column("price_yearly", sa.Numeric(10, 2), default=0.0),
        sa.Column("max_conversations_per_month", sa.Integer, default=500),
        sa.Column("max_tokens_per_month", sa.Integer, default=1_000_000),
        sa.Column("max_agents", sa.Integer, default=3),
        sa.Column("max_api_calls_per_day", sa.Integer, default=1000),
        sa.Column("max_storage_mb", sa.Integer, default=500),
        sa.Column("max_voice_minutes_per_month", sa.Integer, default=0),
        sa.Column("max_team_members", sa.Integer, default=3),
        sa.Column("rate_limit_per_minute", sa.Integer, default=20),
        sa.Column("extra_data", postgresql.JSONB, default={}),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("is_public", sa.Boolean, default=True),
        sa.Column("sort_order", sa.Integer, default=0),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=True),
    )

    # ── subscriptions ─────────────────────────────────────────────────────────
    op.create_table(
        "subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False, unique=True),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("subscription_plans.id"), nullable=False),
        sa.Column("stripe_customer_id", sa.String(255), nullable=True),
        sa.Column("stripe_subscription_id", sa.String(255), nullable=True, unique=True),
        sa.Column("status", sa.String(50), default="active"),
        sa.Column("billing_cycle", sa.String(20), default="monthly"),
        sa.Column("trial_ends_at", sa.DateTime, nullable=True),
        sa.Column("current_period_start", sa.DateTime, nullable=True),
        sa.Column("current_period_end", sa.DateTime, nullable=True),
        sa.Column("canceled_at", sa.DateTime, nullable=True),
        sa.Column("cancel_at_period_end", sa.Boolean, default=False),
        sa.Column("extra_data", postgresql.JSONB, default={}),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=True),
    )
    op.create_index("ix_subscriptions_stripe_customer", "subscriptions", ["stripe_customer_id"])
    op.create_index("ix_subscriptions_stripe_sub", "subscriptions", ["stripe_subscription_id"])

    # ── invoices ──────────────────────────────────────────────────────────────
    op.create_table(
        "invoices",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("subscription_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("subscriptions.id"), nullable=True),
        sa.Column("stripe_invoice_id", sa.String(255), unique=True, nullable=False),
        sa.Column("stripe_payment_intent_id", sa.String(255), nullable=True),
        sa.Column("amount_due", sa.Numeric(10, 2), nullable=False),
        sa.Column("amount_paid", sa.Numeric(10, 2), default=0.0),
        sa.Column("currency", sa.String(10), default="usd"),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("invoice_pdf", sa.String(500), nullable=True),
        sa.Column("hosted_invoice_url", sa.String(500), nullable=True),
        sa.Column("period_start", sa.DateTime, nullable=True),
        sa.Column("period_end", sa.DateTime, nullable=True),
        sa.Column("due_date", sa.DateTime, nullable=True),
        sa.Column("paid_at", sa.DateTime, nullable=True),
        sa.Column("line_items", postgresql.JSONB, default=[]),
        sa.Column("extra_data", postgresql.JSONB, default={}),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_invoices_stripe_id", "invoices", ["stripe_invoice_id"])

    # ── payments ──────────────────────────────────────────────────────────────
    op.create_table(
        "payments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("stripe_payment_intent_id", sa.String(255), unique=True, nullable=False),
        sa.Column("stripe_charge_id", sa.String(255), nullable=True),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("currency", sa.String(10), default="usd"),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("failure_code", sa.String(100), nullable=True),
        sa.Column("failure_message", sa.Text, nullable=True),
        sa.Column("extra_data", postgresql.JSONB, default={}),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )

    # ── usage_meters ──────────────────────────────────────────────────────────
    op.create_table(
        "usage_meters",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("period", sa.String(7), nullable=False),
        sa.Column("conversations_count", sa.Integer, default=0),
        sa.Column("total_tokens", sa.Integer, default=0),
        sa.Column("gpt4o_tokens", sa.Integer, default=0),
        sa.Column("gpt4o_mini_tokens", sa.Integer, default=0),
        sa.Column("embedding_tokens", sa.Integer, default=0),
        sa.Column("voice_minutes", sa.Numeric(10, 2), default=0.0),
        sa.Column("storage_mb", sa.Numeric(10, 2), default=0.0),
        sa.Column("api_calls", sa.Integer, default=0),
        sa.Column("total_cost_usd", sa.Numeric(12, 6), default=0.0),
        sa.Column("gpt4o_cost_usd", sa.Numeric(12, 6), default=0.0),
        sa.Column("gpt4o_mini_cost_usd", sa.Numeric(12, 6), default=0.0),
        sa.Column("embedding_cost_usd", sa.Numeric(12, 6), default=0.0),
        sa.Column("voice_cost_usd", sa.Numeric(12, 6), default=0.0),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=True),
        sa.UniqueConstraint("organization_id", "period", name="uq_usage_meters_org_period"),
    )
    op.create_index("ix_usage_meters_org_period", "usage_meters", ["organization_id", "period"])

    # ── tenant_usage ──────────────────────────────────────────────────────────
    op.create_table(
        "tenant_usage",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agents.id"), nullable=True),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("usage_type", sa.String(50), nullable=False),
        sa.Column("model", sa.String(100), nullable=True),
        sa.Column("input_tokens", sa.Integer, default=0),
        sa.Column("output_tokens", sa.Integer, default=0),
        sa.Column("total_tokens", sa.Integer, default=0),
        sa.Column("cost_usd", sa.Numeric(12, 6), default=0.0),
        sa.Column("duration_ms", sa.Integer, default=0),
        sa.Column("voice_seconds", sa.Numeric(10, 2), default=0.0),
        sa.Column("from_cache", sa.Boolean, default=False),
        sa.Column("period", sa.String(7), nullable=False),
        sa.Column("extra_data", postgresql.JSONB, default={}),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_tenant_usage_org_period", "tenant_usage", ["organization_id", "period"])
    op.create_index("ix_tenant_usage_created", "tenant_usage", ["created_at"])

    # ── quota_events ──────────────────────────────────────────────────────────
    op.create_table(
        "quota_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("quota_type", sa.String(50), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("current_value", sa.Numeric(15, 2), nullable=False),
        sa.Column("limit_value", sa.Numeric(15, 2), nullable=False),
        sa.Column("percentage_used", sa.Numeric(5, 2), nullable=False),
        sa.Column("message", sa.Text, nullable=True),
        sa.Column("extra_data", postgresql.JSONB, default={}),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )

    # ── api_usage ─────────────────────────────────────────────────────────────
    op.create_table(
        "api_usage",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("endpoint", sa.String(255), nullable=False),
        sa.Column("method", sa.String(10), nullable=False),
        sa.Column("status_code", sa.Integer, nullable=False),
        sa.Column("response_time_ms", sa.Integer, default=0),
        sa.Column("rate_limit_key", sa.String(255), nullable=True),
        sa.Column("was_rate_limited", sa.Boolean, default=False),
        sa.Column("period", sa.String(7), nullable=False),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column("request_id", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_api_usage_org_period", "api_usage", ["organization_id", "period"])
    op.create_index("ix_api_usage_created", "api_usage", ["created_at"])

    # ── feature_flags ─────────────────────────────────────────────────────────
    op.create_table(
        "feature_flags",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("key", sa.String(100), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("plan_name", sa.String(50), nullable=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=True),
        sa.Column("is_enabled", sa.Boolean, default=False),
        sa.Column("config", postgresql.JSONB, default={}),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=True),
    )
    op.create_index("ix_feature_flags_key", "feature_flags", ["key"])


def downgrade() -> None:
    op.drop_table("feature_flags")
    op.drop_table("api_usage")
    op.drop_table("quota_events")
    op.drop_table("tenant_usage")
    op.drop_table("usage_meters")
    op.drop_table("payments")
    op.drop_table("invoices")
    op.drop_table("subscriptions")
    op.drop_table("subscription_plans")
