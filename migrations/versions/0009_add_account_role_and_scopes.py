"""Persist authorization attributes on ``accounts`` (B4-ter-2, §19.2).

Migration 0006 created ``accounts`` with authentication fields only, so
``role`` and ``scopes`` had nowhere to live: the API stored them in memory and
every DB read had to invent ``operator`` / ``["read", "write"]``. An account
created as ``role=reader`` came back as ``operator`` after a restart.

This revision is purely additive (§41.14): two new columns with server
defaults, so the existing rows keep working and no NOT NULL is added without a
default.

Revision ID: 0009
Revises: 0008
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: str = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Authorization defaults applied to pre-existing rows.
DEFAULT_ROLE = "operator"
DEFAULT_SCOPES = '["read", "write"]'


def upgrade() -> None:
    """Add ``role`` and ``scopes`` to ``accounts`` (purely additive)."""
    op.add_column(
        "accounts",
        sa.Column(
            "role",
            sa.String(50),
            nullable=False,
            server_default=DEFAULT_ROLE,
        ),
    )
    op.add_column(
        "accounts",
        sa.Column(
            "scopes",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text(f"'{DEFAULT_SCOPES}'::jsonb"),
        ),
    )


def downgrade() -> None:
    """Drop the authorization columns (exact reverse, §41.14)."""
    op.drop_column("accounts", "scopes")
    op.drop_column("accounts", "role")
