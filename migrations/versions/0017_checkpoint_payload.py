"""Let a checkpoint carry what the committed steps already produced (§41.1).

Revision ``0005`` created ``execution_checkpoints`` with the *position* of a run
(``last_committed_step``, ``last_committed_at``, ``resume_token``) but not what
the run had acquired when it stopped. Resuming could therefore only restart from
the beginning — and everything acquired before the interruption was lost, which
is exactly what §41.1 forbids.

Two additive columns close that gap:

* ``step_index`` — the ordinal of the last committed step, so a resume can skip
  the committed prefix without re-deriving the plan;
* ``payload`` — the **step results** of the committed prefix. A resumed run
  replays them (they carry the units, sources and findings already acquired)
  instead of re-executing the steps that produced them.

Both columns are nullable with no default change: the upgrade is non-breaking
(§41.14) and a row written before this revision simply has no payload, which the
reader reports as "cannot resume" rather than guessing.

Revision ID: 0017
Revises: 0016
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0017"
down_revision: str = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the committed-prefix payload and its ordinal."""
    op.add_column(
        "execution_checkpoints", sa.Column("step_index", sa.Integer(), nullable=True)
    )
    op.add_column(
        "execution_checkpoints",
        sa.Column("payload", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    """Drop exactly what :func:`upgrade` added (symmetric, §41.14)."""
    op.drop_column("execution_checkpoints", "payload")
    op.drop_column("execution_checkpoints", "step_index")
