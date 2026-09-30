"""Give an ingested document's units and datasets the columns §11/§27 imply.

Revision ``0007`` created ``datasets`` with ``dataset_id``, ``name``,
``source_id``, ``row_count``, ``schema`` and ``created_at``. Three things the
ingestion path needs were missing:

* ``datasets.storage_ref`` — the §1/§27 ``Dataset`` entity carries it, and
  without the column the link to the bytes the rows came from is lost as soon as
  the reader's ``file://`` temporary copy disappears;
* ``datasets.request_id`` (+ index) — a dataset ingested for a request must be
  findable from that request, exactly like an artifact (0013) or a document
  (0014);
* ``information_units.dataset_id`` and ``information_units.location`` — §11 lists
  both, the ingestion fills both (each unit says *where* in the document it is:
  row, section, character offset), and there was nowhere to keep them. A delivery
  could therefore not answer "which rows of which file produced this unit?".

All columns are nullable, so the migration is non-breaking (§41.14).

Revision ID: 0015
Revises: 0014
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015"
down_revision: str = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Named objects this revision creates, so the downgrade removes exactly them.
_DATASET_REQUEST_INDEX = "ix_datasets_request_id"
_UNIT_DATASET_INDEX = "ix_information_units_dataset_id"


def upgrade() -> None:
    """Add the §11/§27 columns the document ingestion needs."""
    op.add_column("datasets", sa.Column("storage_ref", sa.Text(), nullable=True))
    op.add_column("datasets", sa.Column("request_id", sa.String(64), nullable=True))
    op.create_index(_DATASET_REQUEST_INDEX, "datasets", ["request_id"])

    op.add_column("information_units", sa.Column("dataset_id", sa.String(64), nullable=True))
    op.add_column(
        "information_units", sa.Column("location", postgresql.JSONB(), nullable=True)
    )
    op.create_index(_UNIT_DATASET_INDEX, "information_units", ["dataset_id"])


def downgrade() -> None:
    """Drop the columns added by this revision."""
    op.drop_index(_UNIT_DATASET_INDEX, table_name="information_units")
    op.drop_column("information_units", "location")
    op.drop_column("information_units", "dataset_id")

    op.drop_index(_DATASET_REQUEST_INDEX, table_name="datasets")
    op.drop_column("datasets", "request_id")
    op.drop_column("datasets", "storage_ref")
