"""Add V2 completeness columns to crawled_pages

Revision ID: 002_crawler_v2
Revises: 001_saas_billing
Create Date: 2026-01-01 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON

revision = "002_crawler_v2"
down_revision = "001_saas_billing"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("crawled_pages", sa.Column("completeness_score", sa.Float(), nullable=True))
    op.add_column("crawled_pages", sa.Column("extraction_sources", JSON(), nullable=True))


def downgrade():
    op.drop_column("crawled_pages", "extraction_sources")
    op.drop_column("crawled_pages", "completeness_score")
