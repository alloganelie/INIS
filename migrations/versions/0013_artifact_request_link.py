"""Link the §24.2 artifacts to their request and persist their identifier sequence.

Revision ID: 0013
Revises: 0012

Revision ``0005`` created ``artifacts`` as the §24.2 table, but a delivered file
could not be found again:

* nothing recorded **which request** an artifact was delivered for, so
  ``GET /v1/artifacts?request_id=…`` — what the frontend already calls — had
  nothing to filter on;
* nothing recorded **when** it was delivered, so a client could not order the
  artifacts of a request, and §18.1 auditability was incomplete.

The ``ART_{YYYY}_{SEQ6}`` identifier of §24.2 is not a ULID (§0.3 does not cover
it), so it needs its own allocator. ``artifact_id_sequences`` holds one row per
year with the last sequence handed out; the repository increments it inside a
transaction, which is what makes the identifier unique across workers and stable
across restarts. Deriving the sequence from ``COUNT(*)`` would have been a race
and would have re-used identifiers after a deletion.

Both added columns are nullable, so the migration is non-breaking (§41.14):
``created_at`` is written by the application (never back-filled with a guessed
timestamp) and rows written before this revision stay valid.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Named objects this revision creates, so the downgrade can only remove them.
_REQUEST_INDEX = "ix_artifacts_request_id"


def upgrade() -> None:
    """Add the request link and the §24.2 identifier sequence."""
    op.add_column("artifacts", sa.Column("request_id", sa.String(64), nullable=True))
    op.add_column(
        "artifacts",
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index(_REQUEST_INDEX, "artifacts", ["request_id"])

    op.create_table(
        "artifact_id_sequences",
        # ``autoincrement=False``: the year is supplied by the allocator. Left to
        # its default, PostgreSQL would create an unused ``nextval`` sequence for
        # an integer primary key — schema drift with no purpose.
        sa.Column("year", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("last_value", sa.BigInteger(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    """Drop the sequence and the request link added by this revision."""
    op.drop_table("artifact_id_sequences")
    op.drop_index(_REQUEST_INDEX, table_name="artifacts")
    op.drop_column("artifacts", "created_at")
    op.drop_column("artifacts", "request_id")
