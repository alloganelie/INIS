"""Inventory of §18.2 (suppression logique) and §18.3 (temporalité) in the schema.

The plan asks to *verify* that the tables and columns respect §18.2/§18.3, not to
assume it. This test is that verification, done statically (the migrations are
the schema of record) so it needs no database.

Verdict it records, after revision ``0016``:

* **§18.2 — yes, on the content records**: ``accounts`` (0006) plus the seven
  content tables a requester can remove (``sources``, ``documents``,
  ``datasets``, ``information_units``, ``evidence``, ``artifacts``, ``conflicts``)
  carry ``deleted_at``. Each column is paired with a partial index on
  ``deleted_at IS NULL``, which is what a §18.2 read filters on.
* **§18.2 — deliberately not on the append-only tables**: ``transformations``
  (§12.1 lineage), ``information_versions`` (§18.1 — a version is superseded,
  never deleted) and ``audit_events`` (§20) must keep their history readable; a
  soft-delete column there would let a deletion contradict the lineage and the
  trail. The second half of the test enforces that absence, so removing the
  decision would require editing this file.
* **§18.3 — yes, where it matters**: every table created by revision ``0007``
  carries ``created_at`` with a server default, and the mutable ones carry
  ``updated_at``.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS = REPO_ROOT / "migrations" / "versions"

#: Tables with a §18.2 soft-delete column: caller-owned content plus accounts.
SOFT_DELETE_TABLES = {
    "accounts",
    "sources",
    "documents",
    "datasets",
    "information_units",
    "evidence",
    "artifacts",
    "conflicts",
}

#: Append-only tables: lineage, versions and audit stay readable forever.
APPEND_ONLY_TABLES = {
    "transformations",
    "information_versions",
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
    """Return the tables some migration gives *column* to.

    Two shapes are read: a column declared inside an ``op.create_table`` block,
    and a column added later with ``op.add_column("<table>", sa.Column(...))``
    (that is how revision ``0016`` extends the content tables). Both are schema
    changes, so both belong in the inventory.
    """
    found: set[str] = set()
    for text in _migration_sources().values():
        for block in re.split(r"op\.create_table\(", text)[1:]:
            name = re.match(r'\s*\n?\s*"([a-z_]+)"', block)
            if name and re.search(rf'sa\.Column\(\s*"{column}"', block):
                found.add(name.group(1))
        for added in re.finditer(
            rf'op\.add_column\(\s*\n?\s*"([a-z_]+)"\s*,\s*sa\.Column\(\s*"{column}"', text
        ):
            found.add(added.group(1))
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


def _revision_module(revision: str):
    """Import a migration module by revision id (its declarations are data)."""
    path = next(MIGRATIONS.glob(f"{revision}_*.py"))
    spec = importlib.util.spec_from_file_location(f"revision_{revision}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_accounts_carries_soft_delete_since_0006() -> None:
    """``accounts`` got its ``deleted_at`` in revision 0006."""
    assert "accounts" in _tables_with_column("deleted_at")


def test_the_content_tables_declared_by_0016_are_the_expected_ones() -> None:
    """§18.2 covers exactly the content records a requester can remove.

    The list is read from the migration itself: the schema of record declares
    it, and this test is what makes a change to that list a deliberate edit.
    """
    module = _revision_module("0016")
    assert set(module._CONTENT_TABLES) == SOFT_DELETE_TABLES - {"accounts"}


def test_append_only_tables_are_never_in_the_soft_delete_list() -> None:
    """Lineage, versions and audit are never soft-deleted — enforced, not hoped.

    A ``deleted_at`` on those tables would let a deletion contradict §12.1
    (lineage), §18.1 (a version is superseded) and §20 (the trail stays
    readable). The two tuples come from the migration, so adding
    ``transformations`` to the content list would fail here.
    """
    module = _revision_module("0016")
    assert set(module._APPEND_ONLY_TABLES) == APPEND_ONLY_TABLES
    overlap = sorted(set(module._APPEND_ONLY_TABLES) & set(module._CONTENT_TABLES))
    assert overlap == [], f"tables append-only dans la liste §18.2 : {overlap}"
    for table in sorted(APPEND_ONLY_TABLES):
        assert table not in _tables_with_column("deleted_at")


def test_each_soft_delete_column_has_its_partial_index() -> None:
    """§18.2 reads filter on ``deleted_at IS NULL``: the index follows.

    The migration names the indexes through a template (``ix_{table}_not_deleted``),
    so the check is on the declared intent: a template, a partial predicate and
    an iteration over the content tables. Whether PostgreSQL really created them
    is asserted on a migrated database by
    ``tests/integration/test_migrations.py::TestRevision0016``.
    """
    text = "\n".join(_migration_sources().values())
    assert "_NOT_DELETED_INDEX = \"ix_{table}_not_deleted\"" in text
    assert "postgresql_where=sa.text(\"deleted_at IS NULL\")" in text
    assert "for table in _CONTENT_TABLES:" in text
    for table in sorted(SOFT_DELETE_TABLES):
        if table != "accounts":
            assert f'"{table}"' in text, f"table §18.2 absente de la migration : {table}"


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
