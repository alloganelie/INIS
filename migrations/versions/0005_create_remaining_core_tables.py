"""Create remaining core tables required for PHASE-05.5 Lot A.

Revision ID: 0005
Revises: 0004
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0005"
down_revision: str = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the §27 tables defined by the PHASE-05.5 scope."""
    op.create_table(
        "claims",
        sa.Column("claim_id", sa.Text(), primary_key=True),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("information_ids", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("evidence_ids", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("epistemic_status", sa.Text(), nullable=False),
    )
    op.create_table(
        "conflicts",
        sa.Column("conflict_id", sa.Text(), primary_key=True),
        sa.Column("information_a", sa.Text(), nullable=False),
        sa.Column("information_b", sa.Text(), nullable=False),
        sa.Column("difference_type", sa.Text(), nullable=False),
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column("resolution_status", sa.Text(), nullable=False),
        sa.Column("resolution_evidence", postgresql.JSONB(), nullable=False, server_default="[]"),
    )
    op.create_table(
        "artifacts",
        sa.Column("artifact_id", sa.Text(), primary_key=True),
        sa.Column("artifact_type", sa.Text(), nullable=False),
        sa.Column("file_name", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.Text(), nullable=False),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.Text(), nullable=False),
        sa.Column("storage_ref", sa.Text(), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("source_ids", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("dataset_ids", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("transformation_ids", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("quality_score", sa.Float(), nullable=True),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("provenance_complete", sa.Boolean(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
    )
    op.create_table(
        "artifact_versions",
        sa.Column("artifact_version_id", sa.Text(), primary_key=True),
        sa.Column("artifact_id", sa.Text(), nullable=False),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["artifact_id"], ["artifacts.artifact_id"]),
        sa.UniqueConstraint("artifact_id", "version", name="uq_artifact_versions_artifact_version"),
    )
    op.create_table(
        "artifact_lineage",
        sa.Column("artifact_lineage_id", sa.Text(), primary_key=True),
        sa.Column("artifact_id", sa.Text(), nullable=False),
        sa.Column("source_ids", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("dataset_ids", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("transformation_ids", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.ForeignKeyConstraint(["artifact_id"], ["artifacts.artifact_id"]),
    )
    op.create_table(
        "agent_messages",
        sa.Column("message_id", sa.Text(), primary_key=True),
        sa.Column("message_type", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_table(
        "execution_checkpoints",
        sa.Column("checkpoint_id", sa.Text(), primary_key=True),
        sa.Column("request_id", sa.Text(), nullable=False),
        sa.Column("resumable", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_committed_step", sa.Text(), nullable=True),
        sa.Column("last_committed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("resume_token", sa.Text(), nullable=True),
    )
    op.create_table(
        "budget_usage",
        sa.Column("budget_usage_id", sa.Text(), primary_key=True),
        sa.Column("request_id", sa.Text(), nullable=False),
        sa.Column("usage", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("total_cost_usd", sa.Float(), nullable=True),
        sa.Column("recorded_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_table(
        "progress",
        sa.Column("request_id", sa.Text(), primary_key=True),
        sa.Column("steps_total", sa.Integer(), nullable=False),
        sa.Column("steps_done", sa.Integer(), nullable=False),
        sa.Column("current_step", sa.Text(), nullable=True),
        sa.Column("estimated_completion", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("partial_findings_available", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.create_table(
        "access_policies",
        sa.Column("policy_id", sa.Text(), primary_key=True),
        sa.Column("subject", postgresql.JSONB(), nullable=False),
        sa.Column("resource", postgresql.JSONB(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("effect", sa.Text(), nullable=False),
        sa.Column("conditions", postgresql.JSONB(), nullable=False, server_default="{}"),
    )
    op.create_table(
        "security_classifications",
        sa.Column("classification_id", sa.Text(), primary_key=True),
        sa.Column("resource_type", sa.Text(), nullable=False),
        sa.Column("resource_id", sa.Text(), nullable=False),
        sa.Column("sensitivity", sa.Text(), nullable=False),
        sa.Column("pii", sa.Boolean(), nullable=False),
        sa.Column("categories", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.UniqueConstraint("resource_type", "resource_id", name="uq_security_classifications_resource"),
    )


def downgrade() -> None:
    """Drop the PHASE-05.5 core tables in dependency order."""
    op.drop_table("security_classifications")
    op.drop_table("access_policies")
    op.drop_table("progress")
    op.drop_table("budget_usage")
    op.drop_table("execution_checkpoints")
    op.drop_table("agent_messages")
    op.drop_table("artifact_lineage")
    op.drop_table("artifact_versions")
    op.drop_table("artifacts")
    op.drop_table("conflicts")
    op.drop_table("claims")
