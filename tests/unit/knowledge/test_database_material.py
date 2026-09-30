"""§36.7/§11 — ce qu'INIS livre après avoir lu une table PostgreSQL.

``postgres_query`` (§21) sait exécuter un ``SELECT`` en lecture seule ; ce
module répond à la question suivante : *que livre-t-on après avoir interrogé une
table ?* La réponse suit exactement le chemin fichier de L2.3 — un ``Dataset``
qui décrit les lignes et une unité §11 par ligne, chacune localisée
(``kind="row"``), traçable jusqu'à la source lue et jusqu'à l'outil qui l'a lue.

Deux limites assumées, et **dites** :

* aucune table n'est nommée → les tables du schéma ``public`` sont listées et la
  livraison le déclare : lire une table au hasard répondrait à une question que
  personne n'a posée ;
* base injoignable, entrée de vault absente ou requête refusée → **aucune** unité
  et une limitation qui nomme la cause — jamais un dataset vide présenté comme un
  résultat, jamais une recherche web à la place (§0.2, §25.2).

Le moteur est doublé ici (pas de PostgreSQL) : le chemin réel est couvert par
``tests/integration/test_request_database_read_e2e.py``.
"""

from __future__ import annotations

import importlib
from types import SimpleNamespace
from typing import Any, Self

import pytest

#: ``app.tools.database`` re-exports the *function* under the module's name, so the
#: module is fetched from ``sys.modules`` by name instead of by attribute access.
query_module = importlib.import_module("app.tools.database.postgres_query")

from app.connectors.database.source_target import PostgresSourceTarget
from app.core.errors import ValidationError
from app.knowledge.ingestion.database_material import (
    LIST_TABLES_SQL,
    MAX_DATABASE_ROWS,
    QUERY_TOOL,
    load_database_material,
    load_database_material_for_request,
    source_preferences_of,
)

REQUEST_ID = "REQ_01M3Q0000000000000000000AA"
STORAGE_REF = "postgres://analytics/agents"
ROWS = [
    {"city": "Paris", "population": 2145906},
    {"city": "Berlin", "population": 3645000},
]
TABLES = [{"table_name": "agents"}, {"table_name": "cities"}]


class FakeResult:
    """Minimal SQLAlchemy result surface (``mappings().all()``)."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def mappings(self) -> Self:
        return self

    def all(self) -> list[dict[str, Any]]:
        return self._rows


class FakeConnection:
    """Async connection answering the table listing and the table read."""

    def __init__(self, rows: list[dict[str, Any]], tables: list[dict[str, Any]]) -> None:
        self._rows = rows
        self._tables = tables
        self.executions: list[tuple[str, Any]] = []

    async def execute(self, statement: Any, parameters: Any = None) -> FakeResult:
        text = str(statement)
        self.executions.append((text, parameters))
        if "information_schema.tables" in text:
            return FakeResult(self._tables)
        return FakeResult(self._rows)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None


class FakeEngine:
    """Async engine double exposing ``begin()`` only (read-only path)."""

    def __init__(
        self, rows: list[dict[str, Any]] | None = None, tables: list[dict[str, Any]] | None = None
    ) -> None:
        self.connection = FakeConnection(rows or [], tables if tables is not None else TABLES)
        self.begun = 0

    def begin(self) -> FakeConnection:
        self.begun += 1
        return self.connection


class FailingEngine:
    """Engine whose transaction refuses to open (host unreachable, refused login)."""

    def begin(self) -> Any:
        raise OSError("connection refused by db.internal:5432")


def _target(table: str | None = "agents") -> PostgresSourceTarget:
    return PostgresSourceTarget(credential_ref="analytics", table=table)


def _statements(engine: FakeEngine) -> list[str]:
    return [statement for statement, _ in engine.connection.executions]
class TestReadingOneTable:
    """§36.7 — une table lue devient un ``Dataset`` et une unité par ligne."""

    async def test_one_unit_per_row(self) -> None:
        material = await load_database_material(
            _target(), request_id=REQUEST_ID, engine=FakeEngine(ROWS)
        )

        assert material.row_count == 2
        assert len(material.units) == 2
        assert material.dataset is not None
        assert material.dataset["row_count"] == 2

    async def test_the_dataset_points_at_the_read_source(self) -> None:
        material = await load_database_material(
            _target(), request_id=REQUEST_ID, engine=FakeEngine(ROWS)
        )

        assert material.dataset is not None
        assert material.dataset["storage_ref"] == STORAGE_REF
        assert material.dataset["dataset_schema"] == {
            "city": "string",
            "population": "integer",
        }

    async def test_every_unit_is_located_in_the_table(self) -> None:
        """§11 — une unité livrée dit où elle se trouve dans la source lue."""

        material = await load_database_material(
            _target(), request_id=REQUEST_ID, engine=FakeEngine(ROWS)
        )

        assert material.dataset is not None
        dataset_id = material.dataset["dataset_id"]
        assert [unit["location"]["row"] for unit in material.units] == [1, 2]
        for unit in material.units:
            assert unit["location"]["kind"] == "row"
            assert unit["location"]["dataset_id"] == dataset_id
            assert unit["location"]["columns"] == ["city", "population"]
            assert unit["dataset_id"] == dataset_id

    async def test_the_units_name_the_tool_that_read_them(self) -> None:
        """§12.1 — l'unité est attribuée à ``postgres_query``, pas à un lecteur de fichier."""

        material = await load_database_material(
            _target(), request_id=REQUEST_ID, engine=FakeEngine(ROWS)
        )

        for unit in material.units:
            assert unit["provenance"]["method"] == f"app.tools.database.{QUERY_TOOL}"
            assert unit["provenance"]["extracted_from"] == STORAGE_REF
            assert unit["provenance"]["request_id"] == REQUEST_ID
            assert unit["context"]["origin"] == "database_query"

    async def test_the_raw_reference_names_the_table_not_a_document(self) -> None:
        """§11 — le lignage brut parle d'une table : aucun ``document_id`` inventé."""

        material = await load_database_material(
            _target(), request_id=REQUEST_ID, engine=FakeEngine(ROWS)
        )

        raw = material.units[0]["raw_reference"]
        assert raw["source"] == "postgres"
        assert raw["service"] == "postgres:analytics"
        assert raw["table"] == "agents"
        assert raw["storage_ref"] == STORAGE_REF
        assert raw["document_id"] is None

    async def test_the_named_table_is_the_one_read(self) -> None:
        engine = FakeEngine(ROWS)

        await load_database_material(_target(), request_id=REQUEST_ID, engine=engine)

        assert any("SELECT * FROM agents" in statement for statement in _statements(engine))

    async def test_the_read_is_bounded(self) -> None:
        """§41.13 — une table de dix millions de lignes n'est pas un colis."""

        engine = FakeEngine(ROWS)

        await load_database_material(_target(), request_id=REQUEST_ID, engine=engine)

        assert any(
            statement.endswith(f"LIMIT {MAX_DATABASE_ROWS}") for statement in _statements(engine)
        )

    async def test_the_read_and_its_limits_are_read_only(self) -> None:
        """§1.2 — même la lecture nomme un transaction READ ONLY."""

        engine = FakeEngine(ROWS)

        await load_database_material(_target(), request_id=REQUEST_ID, engine=engine)

        assert "SET TRANSACTION READ ONLY" in _statements(engine)

    async def test_the_material_says_what_was_read(self) -> None:
        material = await load_database_material(
            _target(), request_id=REQUEST_ID, engine=FakeEngine(ROWS)
        )

        assert "2 ligne(s)" in material.summary()
        assert "agents" in material.summary()
        assert material.has_material is True

    async def test_the_lineage_names_the_service_and_the_table(self) -> None:
        """§12.1 — la ligne de transformation dit quel service a lu quelle table."""

        material = await load_database_material(
            _target(), request_id=REQUEST_ID, engine=FakeEngine(ROWS)
        )

        lineage = material.lineage()
        assert lineage["service"] == "postgres:analytics"
        assert lineage["table"] == "agents"
        assert lineage["row_count"] == 2
        assert [unit["information_id"] for unit in material.units] == lineage["unit_ids"]
class TestWhenNoTableIsNamed:
    """§7/§36.7 — lire une table au hasard répondrait à une question non posée."""

    async def test_the_public_tables_are_listed(self) -> None:
        material = await load_database_material(
            _target(table=None), request_id=REQUEST_ID, engine=FakeEngine(tables=TABLES)
        )

        assert material.tables == ("agents", "cities")
        assert material.rows == ()
        assert material.dataset is None
        assert material.units == ()

    async def test_only_the_public_schema_is_offered(self) -> None:
        """Lister tout le serveur exposerait des schémas que la requête n'a pas nommés."""

        engine = FakeEngine(tables=TABLES)

        await load_database_material(_target(table=None), request_id=REQUEST_ID, engine=engine)

        assert any("table_schema = 'public'" in statement for statement in _statements(engine))

    async def test_the_limitation_says_how_to_name_the_table(self) -> None:
        material = await load_database_material(
            _target(table=None), request_id=REQUEST_ID, engine=FakeEngine(tables=TABLES)
        )

        assert len(material.limitations) == 1
        assert "postgres:analytics#<table>" in material.limitations[0]

    async def test_nothing_is_deliverable_without_a_table(self) -> None:
        material = await load_database_material(
            _target(table=None), request_id=REQUEST_ID, engine=FakeEngine(tables=TABLES)
        )

        assert material.has_rows is False
        assert material.has_material is False

    async def test_the_listing_is_a_bounded_read(self) -> None:
        material = await load_database_material(
            _target(table=None), request_id=REQUEST_ID, engine=FakeEngine(tables=TABLES)
        )

        assert "information_schema.tables" in LIST_TABLES_SQL
        assert "2 table(s)" in material.summary()


class TestWhenTheReadFails:
    """§0.2/§25.2 — un échec produit une limitation nommée, jamais un dataset vide."""

    async def test_an_unreachable_database_names_the_cause(self) -> None:
        material = await load_database_material(
            _target(), request_id=REQUEST_ID, engine=FailingEngine()
        )

        assert material.dataset is None
        assert material.units == ()
        assert material.has_material is False
        assert "n'a pas pu être lue" in material.limitations[0]

    async def test_a_refused_statement_yields_no_material(self) -> None:
        """Une borne invalide est refusée **avant** toute connexion (§1.2, §19)."""

        engine = FakeEngine(ROWS)

        material = await load_database_material(
            _target(), request_id=REQUEST_ID, engine=engine, max_rows=0
        )

        assert material.dataset is None
        assert material.units == ()
        assert material.limitations
        assert engine.begun == 0

    async def test_the_failure_is_expressed_in_the_summary(self) -> None:
        material = await load_database_material(
            _target(), request_id=REQUEST_ID, engine=FailingEngine()
        )

        assert "aucune matière lue" in material.summary()

    async def test_the_transaction_is_opened_once(self) -> None:
        """§41.13 — une lecture consomme une seule transaction, refermée avec elle."""

        engine = FakeEngine(ROWS)

        await load_database_material(_target(), request_id=REQUEST_ID, engine=engine)

        assert engine.begun == 1


class TestAnEmptyTable:
    """§24.3 — une table vide n'est pas un résultat : elle est dite vide."""

    async def test_no_dataset_is_fabricated(self) -> None:
        material = await load_database_material(
            _target(), request_id=REQUEST_ID, engine=FakeEngine(rows=[])
        )

        assert material.dataset is None
        assert material.units == ()
        assert material.has_material is False

    async def test_the_limitation_says_the_table_is_empty(self) -> None:
        material = await load_database_material(
            _target(), request_id=REQUEST_ID, engine=FakeEngine(rows=[])
        )

        assert "aucune ligne" in material.limitations[0]
class TestWhichDatabaseIsRead:
    """§41.4 — la base lue est celle de l'entrée du vault, jamais celle d'INIS."""

    async def test_no_engine_means_the_vault_names_the_database(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("INIS_DATABASE_URL", "postgresql+asyncpg://inis:pw@inis-db:5432/inis")
        monkeypatch.setenv(
            "INIS_CRED_ANALYTICS", '{"dsn": "postgresql+asyncpg://src:pw@client-db:5432/ag"}'
        )
        engine = FakeEngine(ROWS)
        captured: list[str] = []

        def _resolve(engine_arg: Any, url: str | None, *, component: str) -> FakeEngine:
            captured.append(str(url))
            return engine_arg if engine_arg is not None else engine

        monkeypatch.setattr(query_module, "resolve_engine", _resolve)

        await load_database_material(_target(), request_id=REQUEST_ID)

        assert captured == ["postgresql+asyncpg://src:pw@client-db:5432/ag"]

    async def test_an_absent_vault_entry_is_a_named_limitation(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """§25.2 — l'entrée à poser est nommée, la requête n'est pas un DSN."""
        monkeypatch.setenv("INIS_DATABASE_URL", "postgresql+asyncpg://inis:pw@inis-db:5432/inis")
        monkeypatch.delenv("INIS_CRED_ANALYTICS", raising=False)

        material = await load_database_material(_target(), request_id=REQUEST_ID)

        assert "INIS_CRED_ANALYTICS" in material.limitations[0]
        assert material.dataset is None

    async def test_a_given_engine_is_used_as_is(self) -> None:
        """Un appelant interne (job, test) peut fournir son moteur (§21)."""
        engine = FakeEngine(ROWS)

        material = await load_database_material(
            _target(), request_id=REQUEST_ID, engine=engine
        )

        assert engine.begun == 1
        assert material.row_count == 2


class TestTheSourceARequestNames:
    """§7 — ``constraints.source_preferences`` est le seul canal du client."""

    def test_a_wire_payload_is_read(self) -> None:
        payload = {"constraints": {"source_preferences": ["web", "postgres:analytics"]}}

        assert source_preferences_of(payload) == ("web", "postgres:analytics")

    def test_a_domain_request_is_read_the_same_way(self) -> None:
        """Le pipeline reçoit le schéma filaire *ou* l'objet du domaine (§32)."""

        payload = SimpleNamespace(
            constraints=SimpleNamespace(source_preferences=["postgres:analytics#agents"])
        )

        assert source_preferences_of(payload) == ("postgres:analytics#agents",)

    def test_no_constraints_means_no_preference(self) -> None:
        assert source_preferences_of({"objective": "x"}) == ()
        assert source_preferences_of(None) == ()

    def test_a_request_without_source_preferences_names_nothing(self) -> None:
        assert source_preferences_of({"constraints": {}}) == ()

    async def test_a_request_that_names_no_database_is_not_touched(self) -> None:
        """Aucune préférence PostgreSQL → aucune connexion, aucun matériel."""

        assert (
            await load_database_material_for_request(
                {"constraints": {"source_preferences": ["web"]}}, request_id=REQUEST_ID
            )
            is None
        )

    async def test_a_named_source_is_read(self) -> None:
        material = await load_database_material_for_request(
            {"constraints": {"source_preferences": ["postgres:analytics#agents"]}},
            request_id=REQUEST_ID,
            engine=FakeEngine(ROWS),
        )

        assert material is not None
        assert material.row_count == 2
        assert material.target.table == "agents"

    async def test_a_malformed_preference_fails_loudly(self) -> None:
        """§25.2 — une faute de frappe ne devient pas « aucune base nommée »."""

        with pytest.raises(ValidationError):
            await load_database_material_for_request(
                {"constraints": {"source_preferences": ["postgres:"]}},
                request_id=REQUEST_ID,
                engine=FakeEngine(ROWS),
            )

    async def test_the_read_uses_the_engine_it_was_given(self) -> None:
        """§41.13 — la lecture partage le pool du déploiement, elle n'en ouvre pas un second."""

        engine = FakeEngine(ROWS)

        await load_database_material_for_request(
            {"constraints": {"source_preferences": ["postgres:analytics#agents"]}},
            request_id=REQUEST_ID,
            engine=engine,
        )

        assert engine.begun == 1