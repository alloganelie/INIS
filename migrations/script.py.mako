"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

Every INIS revision is additive and nullable-only when it touches an existing
table: adding an optional column or an index is a non-breaking migration,
whereas a rename/drop needs a compatibility window (§41.14,
``scripts/check_backward_compat.py``).
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision: str = ${repr(up_revision)}
down_revision: str | Sequence[str] | None = ${repr(down_revision)}
branch_labels: str | Sequence[str] | None = ${repr(branch_labels)}
depends_on: str | Sequence[str] | None = ${repr(depends_on)}


def upgrade() -> None:
    """Apply the revision."""
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    """Revert the revision."""
    ${downgrades if downgrades else "pass"}

