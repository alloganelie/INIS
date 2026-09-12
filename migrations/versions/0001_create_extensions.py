"""Create PostgreSQL extensions for INIS.

Revision ID: 0001
Revises:
Create Date: 2024-09-12

This migration creates the required PostgreSQL extensions:
- uuid-ossp: UUID generation functions
- pgcrypto: cryptographic functions
- vector: pgvector for similarity search (per §16.1)
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create PostgreSQL extensions."""
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "vector"')


def downgrade() -> None:
    """Drop PostgreSQL extensions."""
    op.execute('DROP EXTENSION IF EXISTS "vector"')
    op.execute('DROP EXTENSION IF EXISTS "pgcrypto"')
    op.execute('DROP EXTENSION IF EXISTS "uuid-ossp"')
