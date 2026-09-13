"""Create transformations table for INIS provenance per section 12.1.

Revision ID: 0004
Revises: 0003
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0004"
down_revision: str = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the backward-compatible transformations table."""
    op.create_table(
        "transformations",
        sa.Column("transformation_id", sa.Text(), primary_key=True),
        sa.Column("input_ids", postgresql.JSONB(), nullable=False),
        sa.Column("output_ids", postgresql.JSONB(), nullable=False),
        sa.Column("operator", sa.Text(), nullable=True),
        sa.Column("tool", sa.Text(), nullable=True),
        sa.Column("tool_version", sa.Text(), nullable=True),
        sa.Column(
            "parameters",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "timestamp",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("justification", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    """Drop the transformations table."""
    op.drop_table("transformations")
