"""Create embeddings table and add full-text search per §16.

Revision ID: 0003
Revises: 0002
Create Date: 2024-09-13

This migration creates:
- embeddings table per §16.1 with HNSW index
- search_vector column on information_units with GIN index
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0003"
down_revision: str = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create embeddings table and add full-text search."""
    # Create embeddings table per §16.1 using raw SQL for pgvector type
    op.execute("""
        CREATE TABLE embeddings (
            embedding_id UUID PRIMARY KEY,
            owner_type TEXT NOT NULL,
            owner_id TEXT NOT NULL,
            model TEXT NOT NULL,
            vector vector(1536) NOT NULL,
            metadata JSONB NOT NULL DEFAULT '{}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    # Create HNSW index on vector column (pgvector)
    # Note: This will need pgvector extension to be installed
    op.execute('CREATE INDEX embeddings_vector_idx ON embeddings USING hnsw (vector vector_cosine_ops)')

    # Add search_vector column to information_units for full-text search
    op.execute('ALTER TABLE information_units ADD COLUMN search_vector TSVECTOR')

    # Create GIN index on search_vector
    op.execute('CREATE INDEX information_units_search_vector_idx ON information_units USING GIN (search_vector)')


def downgrade() -> None:
    """Drop embeddings table and full-text search."""
    op.execute('DROP INDEX IF EXISTS information_units_search_vector_idx')
    op.execute('ALTER TABLE information_units DROP COLUMN IF EXISTS search_vector')
    op.execute('DROP INDEX IF EXISTS embeddings_vector_idx')
    op.execute('DROP TABLE IF EXISTS embeddings')
