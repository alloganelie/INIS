"""Maintain ``information_units.search_vector`` on write (§16.1).

Revision ID: 0012
Revises: 0011

Revision 0003 added the ``search_vector`` column and its GIN index, but nothing
ever filled it: the application inserts omit the column, so the lexical half of
§16.2 (``fulltext_search`` / ``hybrid_search``) returned zero rows on real
pipeline output. This revision adds the missing writer — a PostgreSQL trigger
over ``information_units.content`` — and backfills the rows already stored.

The trigger only fills a *NULL* vector: an explicit ``search_vector`` (the §16
integration corpus) is preserved verbatim. ``to_tsvector`` is called without an
explicit configuration so it uses ``default_text_search_config``, exactly like
the ``plainto_tsquery(:query)`` of the search statements: the two sides of the
match are then computed with the same configuration.
"""

from typing import Sequence

from alembic import op


revision: str = "0012"
down_revision: str = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


#: Fills a NULL ``search_vector`` from the JSONB ``content`` payload.
_FUNCTION_SQL = """
CREATE OR REPLACE FUNCTION inis_information_units_tsv() RETURNS trigger AS $$
BEGIN
    IF NEW.search_vector IS NULL THEN
        NEW.search_vector := to_tsvector(COALESCE(NEW.content::text, ''));
    END IF;
    RETURN NEW;
END
$$ LANGUAGE plpgsql
"""

#: Fires on every application insert/update of the indexed payload.
_TRIGGER_SQL = """
CREATE TRIGGER trg_information_units_tsv
    BEFORE INSERT OR UPDATE OF content ON information_units
    FOR EACH ROW EXECUTE FUNCTION inis_information_units_tsv()
"""


def upgrade() -> None:
    """Create the tsvector trigger and backfill existing rows."""
    op.execute(_FUNCTION_SQL)
    op.execute("DROP TRIGGER IF EXISTS trg_information_units_tsv ON information_units")
    op.execute(_TRIGGER_SQL)
    op.execute(
        """
        UPDATE information_units
        SET search_vector = to_tsvector(COALESCE(content::text, ''))
        WHERE search_vector IS NULL
        """
    )


def downgrade() -> None:
    """Drop the trigger, its function and the derived vectors."""
    op.execute("DROP TRIGGER IF EXISTS trg_information_units_tsv ON information_units")
    op.execute("DROP FUNCTION IF EXISTS inis_information_units_tsv()")
    op.execute("UPDATE information_units SET search_vector = NULL")
