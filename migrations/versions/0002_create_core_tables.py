"""Create core tables for INIS per §27.

Revision ID: 0002
Revises: 0001
Create Date: 2024-09-13

This migration creates the core tables:
- agents (per §6.1)
- sources
- documents
- information_units
- audit_events (per §20.1)
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0002"
down_revision: str = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create core tables."""
    # Create agents table per §6.1
    op.create_table(
        "agents",
        sa.Column("agent_id", sa.Text(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("protocols", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("capabilities", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("health", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("registered_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_seen_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # Create sources table
    op.create_table(
        "sources",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("reliability_score", sa.Float(), nullable=True),
        sa.Column("freshness", postgresql.JSONB(), nullable=True),
        sa.Column("data_stage", sa.Text(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # Create documents table
    op.create_table(
        "documents",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("source_id", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column("storage_ref", sa.Text(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"]),
    )
    op.create_foreign_key("fk_documents_source_id", "documents", "sources", ["source_id"], ["id"])

    # Create information_units table
    op.create_table(
        "information_units",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("content", postgresql.JSONB(), nullable=False),
        sa.Column("source_id", sa.Text(), nullable=False),
        sa.Column("document_id", sa.Text(), nullable=True),
        sa.Column("data_stage", sa.Text(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"]),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"]),
    )
    op.create_foreign_key("fk_information_units_source_id", "information_units", "sources", ["source_id"], ["id"])
    op.create_foreign_key("fk_information_units_document_id", "information_units", "documents", ["document_id"], ["id"])

    # Create audit_events table per §20.1
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("timestamp", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("actor_type", sa.Text(), nullable=False),
        sa.Column("actor_id", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("resource_type", sa.Text(), nullable=False),
        sa.Column("resource_id", sa.Text(), nullable=False),
        sa.Column("request_id", sa.Text(), nullable=True),
        sa.Column("result", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("before_hash", sa.Text(), nullable=True),
        sa.Column("after_hash", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    """Drop core tables."""
    op.drop_constraint("fk_information_units_document_id", "information_units")
    op.drop_constraint("fk_information_units_source_id", "information_units")
    op.drop_constraint("fk_documents_source_id", "documents")
    op.drop_table("audit_events")
    op.drop_table("information_units")
    op.drop_table("documents")
    op.drop_table("sources")
    op.drop_table("agents")
