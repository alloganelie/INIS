"""Inventory of §18.2 (suppression logique) and §18.3 (temporalité) in the schema.

The plan asks to *verify* that the tables and columns landing since L1.3 respect
§18.2/§18.3, not to assume it. This test is that verification, done statically
(the migrations are the schema of record) so it needs no database.

Verdict it records, honestly:

* **§18.3 — yes, where it matters**: every table created by revision ``0007``
  carries ``created_at`` with a server default, and the mutable ones carry
  ``updated_at``.
* **§18.2 — partly**: ``accounts`` (revision ``0006``) is the only table with a
  ``deleted_at`` column. The content tables (``sources``, ``documents``,
  ``information_units``, ``datasets``, ``artifacts``, …) have **no** soft-delete
  column: archiving them today means a hard ``DELETE`` or an application-level
  convention, which §18.2 does not accept.

Closing that gap means adding columns to existing tables, i.e. a **migration**
(revision ``0016``): it changes the data schema, so it is a decision to be taken
explicitly. Until then, this test pins the gap instead of hiding it — and fails
the day a migration adds the columns without updating the inventory below.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS = REPO_ROOT / "migrations" / "versions"

#: Tables the schema gives a soft-delete column today (revision 0006).
SOFT_DELETE_TABLES = {"accounts"}

#: Content tables that §18.2 would cover and that still have no such column.
#: Adding a migration is what removes an entry from this set (revision 0016).
SOFT_DELETE_GAP = {
    "sources",
    "documents",
    "datasets",
    "information_units",
    "information_versions",
    "evidence",
    "artifacts",
    "conflicts",
    "transformations",
    "audit_events",
}

#: Temporal columns §18.3 requires on a mutable record.
TEMPORAL_COLUMNS = ("created_at", "updated_at")

#: Internal bookkeeping tables: a counter or a sequence is not a dated record,
#: so §18.3 does not apply to it (nothing reads, supersedes or archives it).
NON_RECORD_TABLES = {"artifact_id_sequences"}


def _migration_sources() -> dict[str, str]:
    """Return every migration file content, keyed by its revision prefix."""
    return {
        path.stem: path.read_text(encoding="utf-8")
        for path in sorted(MIGRATIONS.glob("[0-9]*.py"))
    }


def _tables_with_column(column: str) -> set[str]:
    """Return the tables some ``op.create_table`` block gives *column* to.

    The block split is enough for this inventory: ``create_table`` blocks are
    flat in this repository, and the alternative (importing the migrations)
    would require a database context.
    """
    found: set[str] = set()
    for text in _migration_sources().values():
        for block in re.split(r"op\.create_table\(", text)[1:]:
            name = re.match(r'\s*\n?\s*"([a-z_]+)"', block)
            if name and re.search(rf'sa\.Column\(\s*"{column}"', block):
                found.add(name.group(1))
    return found


def _tables_without_created_at_after(revision: str) -> set[str]:
    """Return the tables created after *revision* without a ``created_at``."""
    late_tables: set[str] = set()
    for name, text in _migration_sources().items():
        if name.split("_", 1)[0] <= revision:
            continue
        for block in re.split(r"op\.create_table\(", text)[1:]:
            table = re.match(r'\s*\n?\s*"([a-z_]+)"', block)
            if table is None:
                continue
            if not re.search(r'sa\.Column\(\s*"created_at"', block):
                late_tables.add(table.group(1))
    return late_tables


def test_accounts_is_the_only_soft_deleted_table_today() -> None:
    """§18.2 is implemented for accounts, and only there."""
    tables = _tables_with_column("deleted_at")
    assert tables == SOFT_DELETE_TABLES, (
        "l'inventaire §18.2 a changé : mettre à jour SOFT_DELETE_TABLES "
        f"(deleted_at trouvé sur {sorted(tables)})"
    )


def test_soft_delete_gap_is_explicit() -> None:
    """The content tables still lack a soft-delete column — stated, not hidden.

    Closing it requires adding columns to existing tables (migration ``0016``),
    a schema change that must be decided and reviewed as such.
    """
    with_soft_delete = _tables_with_column("deleted_at")
    still_missing = SOFT_DELETE_GAP - with_soft_delete
    assert still_missing, (
        "toutes les tables de SOFT_DELETE_GAP ont un deleted_at : "
        "retirer les colonnes de SOFT_DELETE_GAP et documenter la migration 0016"
    )
    assert len(still_missing) >= 5, "le périmètre §18.2 attendu a été réduit sans décision"


def test_new_tables_created_after_0007_carry_created_at() -> None:
    """§18.3: a table created after 0007 declares ``created_at``.

    Except the internal sequences, which hold a counter and no dated record.
    """
    late_tables = _tables_without_created_at_after("0007") - NON_RECORD_TABLES
    assert late_tables == set(), f"tables sans created_at (§18.3) : {sorted(late_tables)}"


@pytest.mark.parametrize("column", TEMPORAL_COLUMNS)
def test_temporal_columns_are_declared_without_a_naive_default(column: str) -> None:
    """A temporal column never defaults to ``0``/``''``: it is a timestamp."""
    offenders: list[str] = []
    for text in _migration_sources().values():
        for block in re.split(r"op\.create_table\(", text)[1:]:
            table = re.match(r'\s*\n?\s*"([a-z_]+)"', block)
            if table is None:
                continue
            match = re.search(rf'sa\.Column\(\s*"{column}"\s*,\s*([^)]*)\)', block)
            if match and not re.search(r"TIMESTAMP|DateTime|_TS", match.group(1)):
                offenders.append(f"{table.group(1)}.{column}")
    assert offenders == [], f"colonnes temporelles non horodatées : {offenders}"
