"""Add PostgreSQL full-text search (BM25) tsvector column and GIN index to document_chunks.

Revision ID: 004_fts_bm25_index
Revises: 003_product_history
Create Date: 2026-01-01 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "004_fts_bm25_index"
down_revision = "003_product_history"
branch_labels = None
depends_on = None


def upgrade():
    # Add generated tsvector column — auto-updated on every content change
    op.execute("""
        ALTER TABLE document_chunks
            ADD COLUMN IF NOT EXISTS fts tsvector
            GENERATED ALWAYS AS (to_tsvector('english', coalesce(content, ''))) STORED
    """)

    # GIN index — required for fast @@ operator queries
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_document_chunks_fts
            ON document_chunks USING GIN(fts)
    """)

    # Composite index for org-scoped FTS queries (most common access pattern)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_document_chunks_org_fts
            ON document_chunks (organization_id)
            WHERE fts IS NOT NULL
    """)


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_org_fts")
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_fts")
    op.execute("ALTER TABLE document_chunks DROP COLUMN IF EXISTS fts")
