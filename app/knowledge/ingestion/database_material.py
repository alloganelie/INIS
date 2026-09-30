"""§36.7/§11 — read one PostgreSQL source and make it deliverable material.

``postgres_query`` (§21) knows how to run a read-only statement; this module
answers the next question: *what does INIS deliver after querying a table?* The
answer follows the file path of L2.3 exactly — a :class:`Dataset` describing the
rows and one §11 unit per row, each located (``kind="row"``), traceable to the
source it was read from and to the tool that read it.

Two deliberate limits, stated rather than hidden:

* when the request named no table, INIS lists the tables of the ``public`` schema
  and says so: reading an arbitrary table would answer a question nobody asked;
* an unreachable database, an absent vault entry or a refused statement yields
  **no** unit and one limitation naming the cause — never an empty dataset
  presented as a result (§0.2, §25.2).

The location of the material is ``postgres://<credential_ref>/<table>``: a
reference to the §41.4 entry, never a DSN and never a secret.

The read itself runs on the DSN held by that vault entry (``INIS_CRED_<REF>``),
not on the deployment's own pool: a source is a database of its own, and reading
INIS's tables while the delivery announces the client's would be a silent
fabrication.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.connectors.database.source_target import PostgresSourceTarget, select_target
from app.core.errors import InisError
from app.domain.value_objects.ulid import ULID
from app.knowledge.ingestion.document_ingestor import record_units
from app.tools.database.postgres_query import DEFAULT_MAX_ROWS, postgres_query
from app.tools.files.dataset_builder import build_dataset

__all__ = [
    "LIST_TABLES_SQL",
    "MAX_DATABASE_ROWS",
    "QUERY_TOOL",
    "DatabaseMaterial",
    "load_database_material",
    "load_database_material_for_request",
    "source_preferences_of",
]

#: §21 tool that reads the database (named in the §12.1 lineage and by §8.4).
QUERY_TOOL = "postgres_query"

#: §41.13 — upper bound on the rows one delivery materialises. A table of ten
#: million rows must not become a colis of ten million units.
MAX_DATABASE_ROWS = 500

#: Table discovery: only the ``public`` schema, and the pattern is bound.
LIST_TABLES_SQL = (
    "SELECT table_name FROM information_schema.tables "
    "WHERE table_schema = 'public' AND table_name LIKE :pattern "
    "ORDER BY table_name"
)

#: Reading one table; the identifier is validated by the target before use.
READ_TABLE_SQL = "SELECT * FROM {table}"


@dataclass(frozen=True)
class DatabaseMaterial:
    """What one PostgreSQL source produced for a delivery (§11/§36.7)."""

    target: PostgresSourceTarget
    source_id: str
    tables: tuple[str, ...] = ()
    rows: tuple[Mapping[str, Any], ...] = ()
    dataset: dict[str, Any] | None = None
    units: tuple[Mapping[str, Any], ...] = ()
    limitations: tuple[str, ...] = ()

    @property
    def has_rows(self) -> bool:
        """Return whether the database returned at least one row."""
        return bool(self.rows)

    @property
    def has_material(self) -> bool:
        """Return whether something of this source can be delivered."""
        return bool(self.rows or self.dataset or self.units)

    @property
    def row_count(self) -> int:
        """Return the number of rows read (never an estimate)."""
        return len(self.rows)

    def summary(self) -> str:
        """Return the factual sentence describing what was read (counts only)."""
        if self.target.table and self.has_rows:
            return (
                f"postgres_query : {self.row_count} ligne(s) lue(s) dans la table "
                f"{self.target.table} de {self.target.describe()} (§36.7)."
            )
        if self.tables:
            return (
                f"postgres_query : {len(self.tables)} table(s) publique(s) listée(s) "
                f"pour {self.target.describe()} (aucune table nommée par la requête)."
            )
        return f"postgres_query : aucune matière lue pour {self.target.describe()}."

    def lineage(self) -> dict[str, Any]:
        """Return the §12.1 description of this read (no content, no secret)."""
        return {
            "service": self.target.service,
            "table": self.target.table,
            "source_ids": [self.source_id],
            "unit_ids": [
                str(unit.get("information_id")) for unit in self.units if unit.get("information_id")
            ],
            "row_count": self.row_count,
        }


def source_preferences_of(payload: Any) -> Sequence[str]:
    """Return ``constraints.source_preferences`` of a request payload.

    Accepts the wire dict (:mod:`app.api.v1.requests.schemas`) and the domain
    value object alike, and never invents a preference when the payload has none.
    """
    if payload is None:
        return ()
    constraints = (
        payload.get("constraints")
        if isinstance(payload, Mapping)
        else getattr(payload, "constraints", None)
    )
    if constraints is None:
        return ()
    preferences = (
        constraints.get("source_preferences")
        if isinstance(constraints, Mapping)
        else getattr(constraints, "source_preferences", None)
    )
    return tuple(preferences or ())


async def load_database_material(
    target: PostgresSourceTarget,
    *,
    request_id: str,
    engine: Any | None = None,
    vault: Any | None = None,
    max_rows: int = MAX_DATABASE_ROWS,
) -> DatabaseMaterial:
    """Read *target* and return its deliverable material (§36.7).

    Args:
        target: The PostgreSQL source named by the request.
        request_id: The request the material belongs to.
        engine: Pre-built engine for the source, used as-is when supplied. Omitted,
            the DSN is read from *target*'s §41.4 vault entry — never from the
            deployment's own pool, which would read INIS's tables instead.
        vault: Vault holding the source credentials (§41.4).
        max_rows: Row cap for one read (§41.13).

    Returns:
        The rows, their ``Dataset``, their §11 units, and the limitations of
        anything that could not be done. Nothing is ever fabricated: a failure
        yields an empty material plus the reason.
    """
    source_id = ULID.new("SRC_")

    if not target.table:
        try:
            tables = await postgres_query(
                LIST_TABLES_SQL,
                {"pattern": "%"},
                credential_ref=target.credential_ref,
                vault=vault,
                engine=engine,
                max_rows=DEFAULT_MAX_ROWS,
            )
        except InisError as exc:
            return DatabaseMaterial(
                target=target,
                source_id=source_id,
                limitations=[f"{target.describe()} n'a pas pu être lue : {exc}"],
            )
        names = tuple(str(row.get("table_name")) for row in tables if row.get("table_name"))
        return DatabaseMaterial(
            target=target,
            source_id=source_id,
            tables=names,
            limitations=[
                (
                    f"Aucune table n'est nommée par la requête : {len(names)} table(s) "
                    f"publique(s) de {target.describe()} sont listées, aucun Dataset n'est "
                    f"livré. Nommer la table voulue : « postgres:{target.credential_ref}"
                    "#<table> » (§7/§36.7)."
                )
            ],
        )

    try:
        rows = await postgres_query(
            READ_TABLE_SQL.format(table=target.table),
            None,
            credential_ref=target.credential_ref,
            vault=vault,
            engine=engine,
            max_rows=max_rows,
        )
    except InisError as exc:
        return DatabaseMaterial(
            target=target,
            source_id=source_id,
            limitations=[f"{target.describe()} n'a pas pu être lue : {exc}"],
        )

    if not rows:
        return DatabaseMaterial(
            target=target,
            source_id=source_id,
            limitations=[
                (
                    f"La table {target.table} de {target.describe()} ne contient aucune "
                    "ligne : aucun Dataset ni unité n'est livré (§24.3)."
                )
            ],
        )

    normalised = [dict(row) for row in rows]
    dataset = build_dataset(
        normalised,
        source_id=source_id,
        storage_ref=target.location,
        dataset_id=ULID.new("DATA_"),
    )
    units = record_units(
        rows=normalised,
        dataset=dataset,
        source_id=source_id,
        request_id=request_id,
        method=f"app.tools.database.{QUERY_TOOL}",
        origin="database_query",
        storage_ref=target.location,
        raw_reference={
            "source": "postgres",
            "service": target.service,
            "table": target.table,
            "storage_ref": target.location,
            "document_id": None,
        },
    )
    return DatabaseMaterial(
        target=target,
        source_id=source_id,
        rows=tuple(normalised),
        dataset=dataset.model_dump(mode="json"),
        units=tuple(units),
    )


async def load_database_material_for_request(
    payload: Any,
    *,
    request_id: str,
    engine: Any | None = None,
    vault: Any | None = None,
    max_rows: int = MAX_DATABASE_ROWS,
) -> DatabaseMaterial | None:
    """Read the PostgreSQL source *payload* names, or ``None`` when it names none.

    Raises:
        ValidationError: When a ``postgres:`` preference is malformed. A typo must
            fail loudly here rather than silently become "no database named".
    """
    target = select_target(source_preferences_of(payload))
    if target is None:
        return None
    return await load_database_material(
        target, request_id=request_id, engine=engine, vault=vault, max_rows=max_rows
    )