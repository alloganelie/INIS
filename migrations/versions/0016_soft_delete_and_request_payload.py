"""§18.2 soft delete on content records, and the §7 request kept whole.

Two gaps this revision closes, both announced as "requires a schema change" by
the L6 report:

* **§18.2 — suppression logique.** Only ``accounts`` had a ``deleted_at``
  (revision 0006). Removing a source, a document, a dataset, an information
  unit, an evidence, an artifact or a conflict meant a hard ``DELETE``, which
  contradicts §18 (a removed record must stay explainable) and destroys the
  provenance a delivery already published.
* **§7 — the request itself.** ``requests`` (0007) stores identity, objective,
  requester, constraints, status and the §41.1 checkpoint. ``question``,
  ``context``, ``required_information``, ``required_output``, ``permissions``
  and ``budget`` had nowhere to live, so a request read back after a restart
  came back with those fields empty. They now travel in ``requests.payload``.

**Scope decision (documented, not accidental).** ``deleted_at`` is added to the
seven *content* tables a requester can remove. It is deliberately **not** added
to the append-only tables — ``transformations`` (§12.1 lineage), ``information_versions``
(a version is superseded, never deleted) and ``audit_events`` (§20 audit) — because
soft-deleting them would let a deletion contradict the lineage and the trail the
spec requires to stay readable. ``tests/unit/migrations/test_soft_delete_columns.py``
enforces both halves of that decision.

Every column is nullable and no default is changed: the upgrade is non-breaking
(§41.14) and no existing row is rewritten. The partial indexes only cover the
rows a reader asks for (``WHERE deleted_at IS NULL``), which is what the §18.2
queries filter on.

⚠️ **BC005** — ``CREATE INDEX`` on a pre-existing table takes a write lock; the
tables here are the ones 0013/0015 already extended (no ``CREATE INDEX
CONCURRENTLY``, which is forbidden inside a transaction). Documented rather than
silently accepted, per the BC005 note.

Revision ID: 0016
Revises: 0015
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016"
down_revision: str = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Content tables a requester can remove: they receive §18.2 soft delete.
_CONTENT_TABLES: tuple[str, ...] = (
    "sources",
    "documents",
    "datasets",
    "information_units",
    "evidence",
    "artifacts",
    "conflicts",
)

#: Append-only tables: lineage (§12.1), versions (§18.1) and audit (§20).
#: They must NOT get ``deleted_at``: a deletion there would rewrite history.
_APPEND_ONLY_TABLES: tuple[str, ...] = (
    "transformations",
    "information_versions",
    "audit_events",
)

#: §18.2 — the partial index a "not deleted" read filters on.
_NOT_DELETED_INDEX = "ix_{table}_not_deleted"


def upgrade() -> None:
    """Add §18.2 soft delete to the content tables and the §7 payload."""
    for table in _CONTENT_TABLES:
        op.add_column(
            table, sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True)
        )
        op.create_index(
            _NOT_DELETED_INDEX.format(table=table),
            table,
            ["deleted_at"],
            postgresql_where=sa.text("deleted_at IS NULL"),
        )

    # §7 — the whole request, so a restart restores what was asked, not a
    # subset. ``NULL`` for the rows created before this revision: the router
    # falls back to the columns it has always written.
    op.add_column(
        "requests", sa.Column("payload", postgresql.JSONB(), nullable=True)
    )


def downgrade() -> None:
    """Remove exactly what :func:`upgrade` added (symmetric, §41.14)."""
    op.drop_column("requests", "payload")

    for table in reversed(_CONTENT_TABLES):
        op.drop_index(_NOT_DELETED_INDEX.format(table=table), table_name=table)
        op.drop_column(table, "deleted_at")
