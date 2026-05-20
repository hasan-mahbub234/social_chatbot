"""Alembic migration — Phase 2 tables: product_snapshots, price_history, stock_history

Revision ID: 003_product_history
Revises: 002_crawler_v2
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSON

revision = "003_product_history"
down_revision = "002_crawler_v2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "product_snapshots",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", sa.String(255), nullable=False, index=True),
        sa.Column("url", sa.Text, nullable=False, index=True),
        sa.Column("canonical_url", sa.Text, nullable=True),
        sa.Column("handle", sa.String(255), nullable=True),
        sa.Column("crawl_job_id", UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.Text, nullable=True),
        sa.Column("price", sa.Float, nullable=True),
        sa.Column("compare_at_price", sa.Float, nullable=True),
        sa.Column("currency", sa.String(10), nullable=True),
        sa.Column("availability", sa.String(50), nullable=True),
        sa.Column("brand", sa.String(255), nullable=True),
        sa.Column("sku", sa.String(255), nullable=True),
        sa.Column("product_type", sa.String(255), nullable=True),
        sa.Column("material", sa.Text, nullable=True),
        sa.Column("color", sa.Text, nullable=True),
        sa.Column("size_options", sa.Text, nullable=True),
        sa.Column("variants_json", JSON, nullable=True),
        sa.Column("completeness_score", sa.Float, nullable=True),
        sa.Column("extraction_sources", JSON, nullable=True),
        sa.Column("price_changed", sa.Boolean, default=False),
        sa.Column("availability_changed", sa.Boolean, default=False),
        sa.Column("variants_changed", sa.Boolean, default=False),
        sa.Column("is_promotion", sa.Boolean, default=False),
        sa.Column("snapshotted_at", sa.DateTime, nullable=False),
    )

    op.create_table(
        "product_price_history",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", sa.String(255), nullable=False, index=True),
        sa.Column("url", sa.Text, nullable=False, index=True),
        sa.Column("sku", sa.String(255), nullable=True),
        sa.Column("old_price", sa.Float, nullable=True),
        sa.Column("new_price", sa.Float, nullable=False),
        sa.Column("currency", sa.String(10), nullable=True),
        sa.Column("compare_at_price", sa.Float, nullable=True),
        sa.Column("is_promotion", sa.Boolean, default=False),
        sa.Column("source", sa.String(50), nullable=True),
        sa.Column("changed_at", sa.DateTime, nullable=False),
    )

    op.create_table(
        "product_stock_history",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", sa.String(255), nullable=False, index=True),
        sa.Column("url", sa.Text, nullable=False, index=True),
        sa.Column("sku", sa.String(255), nullable=True),
        sa.Column("variant_title", sa.String(255), nullable=True),
        sa.Column("old_availability", sa.String(50), nullable=True),
        sa.Column("new_availability", sa.String(50), nullable=False),
        sa.Column("old_stock_level", sa.Integer, nullable=True),
        sa.Column("new_stock_level", sa.Integer, nullable=True),
        sa.Column("source", sa.String(50), nullable=True),
        sa.Column("changed_at", sa.DateTime, nullable=False),
    )

    op.create_index("ix_price_history_url_time", "product_price_history", ["url", "changed_at"])
    op.create_index("ix_stock_history_url_time", "product_stock_history", ["url", "changed_at"])
    op.create_index("ix_snapshots_url_time", "product_snapshots", ["url", "snapshotted_at"])


def downgrade():
    op.drop_table("product_stock_history")
    op.drop_table("product_price_history")
    op.drop_table("product_snapshots")
