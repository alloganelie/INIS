"""Add the §41.5 L2 cache table and the §41.4/§41.7 support tables.

* ``cache_entries`` — L2 (PostgreSQL) cache of validated information units.
* ``delegations``   — §41.10 delegation edges between agents.
* ``protocol_negotiations`` — §41.11 negotiation outcomes per agent.

Purely additive (§41.14): no DROP COLUMN, no ALTER TYPE, no NOT NULL without a
server default.

Revision ID: 0008
Revises: 0007
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: str = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TS = sa.TIMESTAMP(timezone=True)
_JSONB = postgresql.JSONB()


def _ulid(name: str) -> sa.Column:
    """Return a ULID primary key column (Crockford 26 chars, §0.3)."""
    return sa.Column(name, sa.String(64), primary_key=True)


def upgrade() -> None:
    """Create the §41.5 / §41.10 / §41.11 tables (purely additive)."""
    # -- §41.5 L2 cache -------------------------------------------------
    op.create_table(
        "cache_entries",
        _ulid("cache_entry_id"),
        sa.Column("cache_key", sa.String(128), nullable=False, unique=True),
        sa.Column("namespace", sa.String(100), nullable=False, server_default="web"),
        sa.Column("level", sa.String(4), nullable=False, server_default="L2"),
        sa.Column("payload", _JSONB, nullable=True),
        sa.Column("source_id", sa.String(64), nullable=True),
        # §41.5 — reuse is refused when this is older than the threshold.
        sa.Column("source_freshness", _TS, nullable=True),
        sa.Column("expires_at", _TS, nullable=True),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_cache_entries_namespace", "cache_entries", ["namespace"])
    op.create_index("ix_cache_entries_source_id", "cache_entries", ["source_id"])
    op.create_index("ix_cache_entries_expires_at", "cache_entries", ["expires_at"])

    # -- §41.10 delegation topology -------------------------------------
    op.create_table(
        "delegations",
        _ulid("delegation_id"),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column("from_agent_id", sa.String(64), nullable=False),
        sa.Column("to_agent_id", sa.String(64), nullable=False),
        sa.Column("depth", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(40), nullable=False, server_default="pending"),
        sa.Column("trust_level", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("result", _JSONB, nullable=True),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_delegations_request_id", "delegations", ["request_id"])
    op.create_index("ix_delegations_from_agent_id", "delegations", ["from_agent_id"])
    op.create_index("ix_delegations_to_agent_id", "delegations", ["to_agent_id"])

    # -- §41.11 protocol negotiation ------------------------------------
    op.create_table(
        "protocol_negotiations",
        _ulid("negotiation_id"),
        sa.Column("agent_id", sa.String(64), nullable=False),
        sa.Column("peer_version", sa.String(16), nullable=False),
        sa.Column("negotiated_version", sa.String(16), nullable=True),
        sa.Column("compatible", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_protocol_negotiations_agent_id", "protocol_negotiations", ["agent_id"]
    )


def downgrade() -> None:
    """Drop the tables added by revision 0008 (exact reverse, §41.14)."""
    op.drop_index("ix_protocol_negotiations_agent_id", table_name="protocol_negotiations")
    op.drop_table("protocol_negotiations")
    op.drop_index("ix_delegations_to_agent_id", table_name="delegations")
    op.drop_index("ix_delegations_from_agent_id", table_name="delegations")
    op.drop_index("ix_delegations_request_id", table_name="delegations")
    op.drop_table("delegations")
    op.drop_index("ix_cache_entries_expires_at", table_name="cache_entries")
    op.drop_index("ix_cache_entries_source_id", table_name="cache_entries")
    op.drop_index("ix_cache_entries_namespace", table_name="cache_entries")
    op.drop_table("cache_entries")
