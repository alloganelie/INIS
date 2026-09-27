"""Create the missing §27 mandatory tables for INIS v2.0.0.

Adds the 13 tables of INIS_SPEC §27 that were absent from the v1 schema:

agent_capabilities, agent_health, agent_learning_profiles, requests, plans,
plan_steps, executions, iterations, source_versions, datasets,
information_versions, evidence, artifact_delivery_events.

Every table is additive only (no DROP COLUMN, no ALTER TYPE, no NOT NULL
without a server default) so the migration is backward compatible per §41.14.

Revision ID: 0007
Revises: 0006
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TS = sa.TIMESTAMP(timezone=True)
_JSONB = postgresql.JSONB()


def _ulid(name: str) -> sa.Column:
    """Return a ULID primary key column (Crockford 26 chars, §0.3)."""
    return sa.Column(name, sa.String(64), primary_key=True)


def upgrade() -> None:
    """Create the missing §27 tables (purely additive)."""
    # -- Agent registry extensions (§6) ---------------------------------
    op.create_table(
        "agent_capabilities",
        _ulid("capability_id"),
        sa.Column("agent_id", sa.String(64), nullable=False),
        sa.Column("capability", sa.String(200), nullable=False),
        sa.Column("version", sa.String(20), nullable=True),
        sa.Column("registered_at", _TS, nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_agent_capabilities_agent_id", "agent_capabilities", ["agent_id"])

    op.create_table(
        "agent_health",
        _ulid("health_id"),
        sa.Column("agent_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="unknown"),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("checked_at", _TS, nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_agent_health_agent_id", "agent_health", ["agent_id"])

    op.create_table(
        "agent_learning_profiles",
        _ulid("learning_profile_id"),
        sa.Column("agent_id", sa.String(64), nullable=False),
        sa.Column("capability", sa.String(200), nullable=False),
        sa.Column("success_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", _TS, nullable=False, server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_agent_learning_profiles_agent_id", "agent_learning_profiles", ["agent_id"]
    )

    # -- Request lifecycle (§7, §41.1) ----------------------------------
    op.create_table(
        "requests",
        _ulid("request_id"),
        sa.Column("request_type", sa.String(40), nullable=False, server_default="research"),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("requester", _JSONB, nullable=True),
        sa.Column("constraints", _JSONB, nullable=True),
        sa.Column("status", sa.String(40), nullable=False, server_default="received"),
        sa.Column("ttl_seconds", sa.Integer(), nullable=False, server_default="900"),
        # §41.1 — checkpoint of the resumable lifecycle
        sa.Column("resumable", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("last_committed_step", sa.String(64), nullable=True),
        sa.Column("last_committed_at", _TS, nullable=True),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", _TS, nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_requests_status", "requests", ["status"])
    op.create_index("ix_requests_last_committed_step", "requests", ["last_committed_step"])

    # -- Planning (§8, §27) --------------------------------------------
    op.create_table(
        "plans",
        _ulid("plan_id"),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(40), nullable=False, server_default="draft"),
        sa.Column("objective", sa.Text(), nullable=True),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_plans_request_id", "plans", ["request_id"])

    op.create_table(
        "plan_steps",
        _ulid("step_id"),
        sa.Column("plan_id", sa.String(64), nullable=False),
        sa.Column("step_index", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("action", sa.String(200), nullable=False, server_default="collect_information"),
        sa.Column("tool", sa.String(200), nullable=True),
        sa.Column("status", sa.String(40), nullable=False, server_default="pending"),
        sa.Column("inputs", _JSONB, nullable=True),
        sa.Column("result", _JSONB, nullable=True),
    )
    op.create_index("ix_plan_steps_plan_id", "plan_steps", ["plan_id"])

    op.create_table(
        "executions",
        _ulid("execution_id"),
        sa.Column("plan_id", sa.String(64), nullable=False),
        sa.Column("step_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(40), nullable=False, server_default="pending"),
        sa.Column("started_at", _TS, nullable=True),
        sa.Column("completed_at", _TS, nullable=True),
    )
    op.create_index("ix_executions_plan_id", "executions", ["plan_id"])

    op.create_table(
        "iterations",
        _ulid("iteration_id"),
        sa.Column("execution_id", sa.String(64), nullable=False),
        sa.Column("iteration_index", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(40), nullable=False, server_default="pending"),
        sa.Column("cost_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_iterations_execution_id", "iterations", ["execution_id"])

    # -- Content lineage (§11, §12) -------------------------------------
    op.create_table(
        "source_versions",
        _ulid("source_version_id"),
        sa.Column("source_id", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("retrieved_at", _TS, nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_source_versions_source_id", "source_versions", ["source_id"])

    op.create_table(
        "datasets",
        _ulid("dataset_id"),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("source_id", sa.String(64), nullable=True),
        sa.Column("row_count", sa.Integer(), nullable=True),
        sa.Column("schema", _JSONB, nullable=True),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "information_versions",
        _ulid("information_version_id"),
        sa.Column("information_id", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("content", _JSONB, nullable=True),
        sa.Column("superseded", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_information_versions_information_id", "information_versions", ["information_id"]
    )

    op.create_table(
        "evidence",
        _ulid("evidence_id"),
        sa.Column("information_id", sa.String(64), nullable=True),
        sa.Column("source_id", sa.String(64), nullable=True),
        sa.Column("document_id", sa.String(64), nullable=True),
        sa.Column("quote", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_evidence_information_id", "evidence", ["information_id"])
    op.create_index("ix_evidence_source_id", "evidence", ["source_id"])

    op.create_table(
        "artifact_delivery_events",
        _ulid("delivery_event_id"),
        sa.Column("artifact_id", sa.String(64), nullable=False),
        sa.Column("target", sa.Text(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False, server_default="pending"),
        sa.Column("delivered_at", _TS, nullable=True),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_artifact_delivery_events_artifact_id", "artifact_delivery_events", ["artifact_id"]
    )


def downgrade() -> None:
    """Drop the tables added by revision 0007 (exact reverse, §41.14)."""
    for table, index in (
        ("artifact_delivery_events", "ix_artifact_delivery_events_artifact_id"),
        ("evidence", "ix_evidence_source_id"),
        ("information_versions", "ix_information_versions_information_id"),
        ("source_versions", "ix_source_versions_source_id"),
    ):
        op.drop_index(index, table_name=table)
    op.drop_table("artifact_delivery_events")
    op.drop_table("evidence")
    op.drop_table("information_versions")
    op.drop_table("source_versions")
    op.drop_table("datasets")
    op.drop_index("ix_iterations_execution_id", table_name="iterations")
    op.drop_table("iterations")
    op.drop_index("ix_executions_plan_id", table_name="executions")
    op.drop_table("executions")
    op.drop_index("ix_plan_steps_plan_id", table_name="plan_steps")
    op.drop_table("plan_steps")
    op.drop_index("ix_plans_request_id", table_name="plans")
    op.drop_table("plans")
    op.drop_index("ix_requests_last_committed_step", table_name="requests")
    op.drop_index("ix_requests_status", table_name="requests")
    op.drop_table("requests")
    op.drop_index(
        "ix_agent_learning_profiles_agent_id", table_name="agent_learning_profiles"
    )
    op.drop_table("agent_learning_profiles")
    op.drop_index("ix_agent_health_agent_id", table_name="agent_health")
    op.drop_table("agent_health")
    op.drop_index("ix_agent_capabilities_agent_id", table_name="agent_capabilities")
    op.drop_table("agent_capabilities")
