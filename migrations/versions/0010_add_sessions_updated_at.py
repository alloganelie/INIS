"""Add ``updated_at`` to ``sessions`` (B4-ter-3, §19.2).

The model inherits ``TimestampMixin``, but migration 0006 never created the
column, so the ORM and the migrated schema disagreed and B4-bis had to declare
``created_at`` by hand on the model. Revoking a session therefore could not be
timestamped: a support question ("when was this token killed?") had no answer
in the database.

Additive (§41.14): a new column with a ``now()`` server default, NOT NULL is
therefore safe on existing rows.

Revision ID: 0010
Revises: 0009
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0010"
down_revision: str = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add ``updated_at`` to ``sessions`` (purely additive)."""
    op.add_column(
        "sessions",
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )


def downgrade() -> None:
    """Drop ``sessions.updated_at`` (exact reverse, §41.14)."""
    op.drop_column("sessions", "updated_at")
