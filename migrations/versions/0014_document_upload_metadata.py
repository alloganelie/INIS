"""Give an uploaded document the metadata §18.1 and §32 need.

Revision ``0002`` created ``documents`` with the strict minimum a §9 source
produces: an identity, a source, a MIME type, a content hash and a storage
reference. That is enough for a file collected *by* INIS, and not enough for a
file a client **uploads**:

* ``file_name`` — the name the requester used, which is what a human looks for;
* ``size_bytes`` — checked against the §41.2 storage budget at upload time;
* ``request_id`` (+ index) — an upload belongs to a request, and
  ``GET /v1/documents?request_id=`` is how it is found again;
* ``pii_classification`` — §19.4 requires the classification of what was
  received (filename, metadata) to be *recorded*, not just computed.

``uq_documents_request_content`` makes the upload idempotent at the database
level: the same bytes uploaded twice for the same request are one document
(CODING_RULES §1.10). Rows written before this revision keep ``NULL`` in the new
columns, so the migration is non-breaking (§41.14).

Revision ID: 0014
Revises: 0013
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014"
down_revision: str = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Named objects this revision creates, so the downgrade removes exactly them.
_REQUEST_INDEX = "ix_documents_request_id"
_REQUEST_CONTENT_CONSTRAINT = "uq_documents_request_content"


def upgrade() -> None:
    """Add the upload metadata §32 exposes and §19.4 requires."""
    op.add_column("documents", sa.Column("file_name", sa.String(512), nullable=True))
    op.add_column("documents", sa.Column("size_bytes", sa.BigInteger(), nullable=True))
    op.add_column("documents", sa.Column("request_id", sa.String(64), nullable=True))
    op.add_column(
        "documents",
        sa.Column("pii_classification", postgresql.JSONB(), nullable=True),
    )
    op.create_index(_REQUEST_INDEX, "documents", ["request_id"])
    op.create_unique_constraint(
        _REQUEST_CONTENT_CONSTRAINT,
        "documents",
        ["request_id", "content_hash"],
    )


def downgrade() -> None:
    """Drop the upload metadata added by this revision."""
    op.drop_constraint(_REQUEST_CONTENT_CONSTRAINT, "documents", type_="unique")
    op.drop_index(_REQUEST_INDEX, table_name="documents")
    op.drop_column("documents", "pii_classification")
    op.drop_column("documents", "request_id")
    op.drop_column("documents", "size_bytes")
    op.drop_column("documents", "file_name")
