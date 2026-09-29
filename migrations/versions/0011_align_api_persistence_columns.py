"""Align the §27 tables with the columns the API persistence declares.

Revision ID: 0011
Revises: 0010

The §32 repositories (``app/storage/repositories/*``) describe the §9/§11/§14.2
columns that the HTTP contract exposes:

* ``sources`` — ``name``, ``description``, ``trust_level``, ``status``,
  ``metadata`` (§9, ``SourceCreate``);
* ``information_units`` — ``raw_reference``, ``context``, ``language``,
  ``epistemic_status``, ``provenance``, ``updated_at`` (§11);
* ``evidence`` — ``claim_id``, ``transformation_id``, ``strength``,
  ``epistemic_status``, ``provenance`` (§14.2).

Revision 0002/0007 created the minimal relational skeleton, so those columns
were missing from the migrated PostgreSQL schema: ``SELECT name FROM sources``
raised ``UndefinedColumn`` and ``GET /v1/sources/{id}`` answered HTTP 500,
while persisted information units and evidence were unreadable through
``/v1/information/{id}`` and ``/v1/evidence/{id}``.

Every column is nullable: adding an optional column is a non-breaking migration
(§41.14) and rows written by the pipeline before this revision stay valid.
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0011"
down_revision: str = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the §9/§11/§14.2 columns the API contract exposes."""
    # §9 — sources registered through POST /v1/sources
    op.add_column("sources", sa.Column("name", sa.String(255), nullable=True))
    op.add_column("sources", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("sources", sa.Column("trust_level", sa.Float(), nullable=True))
    op.add_column("sources", sa.Column("status", sa.String(64), nullable=True))
    op.add_column("sources", sa.Column("metadata", postgresql.JSONB(), nullable=True))

    # §11 — full InformationUnit payload (context, language, provenance…)
    op.add_column("information_units", sa.Column("raw_reference", postgresql.JSONB(), nullable=True))
    op.add_column("information_units", sa.Column("context", postgresql.JSONB(), nullable=True))
    op.add_column("information_units", sa.Column("language", sa.String(16), nullable=True))
    op.add_column("information_units", sa.Column("epistemic_status", sa.String(32), nullable=True))
    op.add_column("information_units", sa.Column("provenance", postgresql.JSONB(), nullable=True))
    op.add_column(
        "information_units",
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )

    # §14.2 — evidence linked to a claim, a transformation and its strength
    op.add_column("evidence", sa.Column("claim_id", sa.String(64), nullable=True))
    op.add_column("evidence", sa.Column("transformation_id", sa.String(64), nullable=True))
    op.add_column("evidence", sa.Column("strength", sa.Float(), nullable=True))
    op.add_column("evidence", sa.Column("epistemic_status", sa.String(32), nullable=True))
    op.add_column("evidence", sa.Column("provenance", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    """Drop the columns added by this revision."""
    op.drop_column("evidence", "provenance")
    op.drop_column("evidence", "epistemic_status")
    op.drop_column("evidence", "strength")
    op.drop_column("evidence", "transformation_id")
    op.drop_column("evidence", "claim_id")

    op.drop_column("information_units", "updated_at")
    op.drop_column("information_units", "provenance")
    op.drop_column("information_units", "epistemic_status")
    op.drop_column("information_units", "language")
    op.drop_column("information_units", "context")
    op.drop_column("information_units", "raw_reference")

    op.drop_column("sources", "metadata")
    op.drop_column("sources", "status")
    op.drop_column("sources", "trust_level")
    op.drop_column("sources", "description")
    op.drop_column("sources", "name")
