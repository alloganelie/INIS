"""§7/§8.4/§36.7 — une source PostgreSQL nommée remplit le colis de la requête.

``constraints.source_preferences`` est le seul canal dont dispose une requête pour
dire « interroge ma base » (§7). Ce fichier verrouille le câblage de bout en bout
de ce canal : la préférence devient une cible (§36.7), la cible est lue par
``postgres_query``, et sa matière entre dans la livraison — ``datasets[]`` non
vide, unités §11 localisées en ligne, source de type ``database``, transformations
§12.1 du connecteur Postgres — **et** le fait que ``request_type`` oriente le plan
(§7, C4) :

* ``data`` : la base nommée est la source, aucune recherche web n'est lancée ;
* ``research`` : le plan garde ses étapes web et gagne la lecture de la base.

Un échec ne remplace jamais la source par une recherche web : l'étape est
dégradée avec sa cause (§25.2, §37).

Le moteur SQL est doublé ici (pas de PostgreSQL) mais le reste du chemin est réel
— y compris la lecture de la préférence et la construction des unités. Le chemin
complet contre une vraie base est couvert par
``tests/integration/test_request_database_read_e2e.py``.
"""

from __future__ import annotations

from typing import Any, Self
from unittest.mock import AsyncMock

import pytest

from app.api.v1.requests import pipeline_runner as runner_module
from app.api.v1.requests.pipeline_runner import PipelineRunner
from app.core.errors import ValidationError
from app.domain.value_objects.ulid import ULID
from app.knowledge.ingestion.database_material import load_database_material_for_request

OBJECTIVE = "Analyse les agents listés dans notre base analytics"
PREFERENCE = "postgres:analytics#agents"
STORAGE_REF = "postgres://analytics/agents"
ROWS = [
    {"agent_id": "A-1", "city": "Paris", "status": "active"},
    {"agent_id": "A-2", "city": "Berlin", "status": "inactive"},
]
TABLES = [{"table_name": "agents"}, {"table_name": "cities"}]


class FakeResult:
    """Minimal SQLAlchemy result surface (``mappings().all()``)."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def mappings(self) -> FakeResult:
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
@pytest.fixture
def web_doubles(monkeypatch: pytest.MonkeyPatch) -> dict[str, AsyncMock]:
    """Mock the §9/§10 providers so any web call is observable."""
    search = AsyncMock(return_value=[])
    extract = AsyncMock(return_value={})
    monkeypatch.setattr(
        "app.connectors.web.provider_router.ProviderRouter.search", search
    )
    monkeypatch.setattr(
        "app.connectors.web.extractors.wikipedia_extractor.WikipediaExtractor.extract",
        extract,
    )
    return {"search": search, "extract": extract}


@pytest.fixture
def captured_steps(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Capture the step results handed to persistence, without a database."""
    captured: list[dict[str, Any]] = []

    async def _fake_persist(**kwargs: Any) -> tuple[bool, list[str], dict[str, Any]]:
        captured.extend(kwargs.get("step_results") or [])
        return False, [], {
            "audit_event_id": ULID.new("AUD_"),
            "timestamp": "2026-01-01T00:00:00Z",
        }

    monkeypatch.setattr(
        "app.api.v1.requests.pipeline_runner.persist_pipeline_delivery", _fake_persist
    )
    return captured


def _use_engine(monkeypatch: pytest.MonkeyPatch, engine: Any) -> None:
    """Run the real loader against *engine* instead of the deployment's database.

    Everything else is the production path: the preference is parsed here, the
    rows are read through ``postgres_query`` and the units are built by the real
    ``load_database_material``.
    """

    async def _load(payload: Any, *, request_id: str, **_: Any) -> Any:
        return await load_database_material_for_request(
            payload, request_id=request_id, engine=engine
        )

    monkeypatch.setattr(runner_module, "load_database_material_for_request", _load)


def _refuse_source(monkeypatch: pytest.MonkeyPatch, message: str) -> None:
    """Make the loader reject the preference, as a malformed entry does."""

    async def _load(payload: Any, *, request_id: str, **_: Any) -> Any:
        raise ValidationError(message)

    monkeypatch.setattr(runner_module, "load_database_material_for_request", _load)


async def _run(
    request_type: str = "data", constraints: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Run the pipeline for one request naming the PostgreSQL source."""
    payload: dict[str, Any] = {"objective": OBJECTIVE, "request_type": request_type}
    if constraints is not None:
        payload["constraints"] = constraints
    return await PipelineRunner().run(ULID.new("REQ_"), payload)


def _stages(delivery: dict[str, Any]) -> list[tuple[str, str]]:
    """Return the (stage, tool) pairs of the delivered §12.1 transformations."""
    return [
        (item["parameters"]["stage"], item["tool"])
        for item in delivery["transformations"]
    ]


def _db_units(delivery: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the delivered units that carry the rows read from PostgreSQL."""
    return [
        unit
        for unit in delivery["information_units"]
        if unit.get("provenance", {}).get("method") == "app.tools.database.postgres_query"
    ]


def _database_step(captured: list[dict[str, Any]]) -> dict[str, Any]:
    """Return the recorded ``query_database`` step result."""
    return next(step for step in captured if step.get("action") == "query_database")
class TestADataRequestIsPlannedAroundItsDatabase:
    """§7 — « data » veut dire : la source, c'est la base nommée."""

    async def test_the_rows_are_delivered_as_a_dataset(
        self,
        web_doubles: dict[str, AsyncMock],
        mock_llm: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _use_engine(monkeypatch, FakeEngine(ROWS))

        delivery = await _run("data", {"source_preferences": [PREFERENCE]})

        assert len(delivery["datasets"]) == 1
        assert delivery["datasets"][0]["row_count"] == 2
        assert delivery["datasets"][0]["storage_ref"] == STORAGE_REF

    async def test_the_units_are_delivered_and_locatable(
        self,
        web_doubles: dict[str, AsyncMock],
        mock_llm: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """§11 — chaque ligne lue devient une unité localisée et traçable."""
        _use_engine(monkeypatch, FakeEngine(ROWS))

        delivery = await _run("data", {"source_preferences": [PREFERENCE]})

        units = _db_units(delivery)
        assert len(units) == 2
        for unit in units:
            assert unit["location"]["kind"] == "row"
            assert unit["location"]["row"] in (1, 2)
            assert unit["dataset_id"] == delivery["datasets"][0]["dataset_id"]
            assert unit["provenance"]["extracted_from"] == STORAGE_REF
            assert unit["context"]["origin"] == "database_query"

    async def test_the_database_is_delivered_as_a_source(
        self,
        web_doubles: dict[str, AsyncMock],
        mock_llm: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """§36.7 — la base est une source du colis, de type ``database``."""
        _use_engine(monkeypatch, FakeEngine(ROWS))

        delivery = await _run("data", {"source_preferences": [PREFERENCE]})

        databases = [
            source
            for source in delivery["sources"]
            if source.get("source_type") == "database"
        ]
        assert len(databases) == 1
        assert databases[0]["url"] == STORAGE_REF
        assert "agents" in databases[0]["name"]

    async def test_no_web_search_is_launched(
        self,
        web_doubles: dict[str, AsyncMock],
        mock_llm: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """§7/§8.4 — chercher sur le web des données que le demandeur détient déjà."""
        _use_engine(monkeypatch, FakeEngine(ROWS))

        await _run("data", {"source_preferences": [PREFERENCE]})

        assert web_doubles["search"].await_count == 0

    async def test_the_step_reports_the_rows_it_read(
        self,
        web_doubles: dict[str, AsyncMock],
        captured_steps: list[dict[str, Any]],
        mock_llm: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """§37 — le résultat d'étape est un compte réel, pas une phrase générique."""
        _use_engine(monkeypatch, FakeEngine(ROWS))

        await _run("data", {"source_preferences": [PREFERENCE]})

        step = _database_step(captured_steps)
        assert step["status"] == "done"
        assert "2 ligne(s)" in step["output"]
        assert step["tools_required"] == ["postgres_query"]

    async def test_the_lineage_names_the_query_tool(
        self,
        web_doubles: dict[str, AsyncMock],
        mock_llm: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """§12.1 — deux étages Postgres, produits par ``postgres_query``."""
        _use_engine(monkeypatch, FakeEngine(ROWS))

        delivery = await _run("data", {"source_preferences": [PREFERENCE]})

        stages = _stages(delivery)
        assert ("raw", "postgres_query") in stages
        assert ("normalized", "postgres_query") in stages
        origins = {
            item["parameters"].get("origin")
            for item in delivery["transformations"]
            if item["tool"] == "postgres_query"
        }
        assert origins == {"database_query"}


class TestWhenTheSourceCannotBeRead:
    """§25.2/§37 — un échec est dit, et ne devient jamais une recherche web."""

    async def test_the_step_is_degraded_with_the_cause(
        self,
        web_doubles: dict[str, AsyncMock],
        captured_steps: list[dict[str, Any]],
        mock_llm: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _use_engine(monkeypatch, FailingEngine())

        await _run("data", {"source_preferences": [PREFERENCE]})

        step = _database_step(captured_steps)
        assert step["status"] == "degraded"
        assert step["output"] == ""
        assert "n'a pas pu être lue" in step["error"]

    async def test_no_dataset_is_delivered(
        self,
        web_doubles: dict[str, AsyncMock],
        mock_llm: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _use_engine(monkeypatch, FailingEngine())

        delivery = await _run("data", {"source_preferences": [PREFERENCE]})

        assert delivery["datasets"] == []
        assert _db_units(delivery) == []

    async def test_the_delivery_states_why_nothing_was_read(
        self,
        web_doubles: dict[str, AsyncMock],
        mock_llm: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _use_engine(monkeypatch, FailingEngine())

        delivery = await _run("data", {"source_preferences": [PREFERENCE]})

        assert any("n'a pas pu être lue" in text for text in delivery["limitations"])
        assert any("query_database" in text for text in delivery["limitations"])

    async def test_the_web_does_not_replace_the_named_source(
        self,
        web_doubles: dict[str, AsyncMock],
        mock_llm: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _use_engine(monkeypatch, FailingEngine())

        await _run("data", {"source_preferences": [PREFERENCE]})

        assert web_doubles["search"].await_count == 0

    async def test_an_empty_table_is_not_a_result(
        self,
        web_doubles: dict[str, AsyncMock],
        captured_steps: list[dict[str, Any]],
        mock_llm: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """§24.3 — une table vide est dite vide, elle n'est pas livrée comme un dataset."""
        _use_engine(monkeypatch, FakeEngine(rows=[]))

        delivery = await _run("data", {"source_preferences": [PREFERENCE]})

        assert delivery["datasets"] == []
        assert _database_step(captured_steps)["status"] == "degraded"
        assert any("aucune ligne" in text for text in delivery["limitations"])

    async def test_a_table_that_is_not_named_is_listed_not_read(
        self,
        web_doubles: dict[str, AsyncMock],
        captured_steps: list[dict[str, Any]],
        mock_llm: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """§36.7 — sans table nommée, INIS liste les tables et le déclare."""
        _use_engine(monkeypatch, FakeEngine(tables=TABLES))

        delivery = await _run("data", {"source_preferences": ["postgres:analytics"]})

        assert delivery["datasets"] == []
        assert _database_step(captured_steps)["status"] == "degraded"
        assert any("postgres:analytics#<table>" in text for text in delivery["limitations"])

    async def test_a_malformed_preference_is_not_silently_ignored(
        self,
        web_doubles: dict[str, AsyncMock],
        captured_steps: list[dict[str, Any]],
        mock_llm: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """§7 — une faute de frappe est un échec nommé, pas « aucune base »."""
        _refuse_source(monkeypatch, "préférence inutilisable")

        delivery = await _run("data", {"source_preferences": ["postgres:"]})

        assert any("inutilisable" in text for text in delivery["limitations"])
        assert _database_step(captured_steps)["status"] == "degraded"
        assert web_doubles["search"].await_count == 0


class TestBothOwnedSourcesCoexist:
    """§7/§8.4 — un fichier *et* une base nommés : les deux sources sont lues."""

    @pytest.fixture
    def ingested_file(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Replace the file-material loader: this request ingested one CSV too."""

        async def _load(request_id: str, **_: Any) -> Any:
            from app.knowledge.ingestion.request_material import (
                RequestMaterial,
                to_delivery_unit,
            )

            document_id = "DOC_01M3Q0000000000000000000AA"
            source_id = "SRC_01M3Q0000000000000000000AA"
            dataset_id = "DATA_01M3Q0000000000000000000AA"
            storage_ref = "s3://inis-artifacts/documents/cities.csv"
            unit = {
                "information_id": "INF_01M3Q0000000000000000000BB",
                "type": "record",
                "content": {"values": {"city": "Paris"}},
                "raw_reference": {"document_id": document_id},
                "source_id": source_id,
                "document_id": document_id,
                "dataset_id": dataset_id,
                "location": {"kind": "row", "row": 1, "columns": ["city"]},
                "context": {"origin": "uploaded_document"},
                "provenance": {"extracted_from": storage_ref, "method": "read_csv"},
                "data_stage": "raw",
                "epistemic_status": "factual",
            }
            return RequestMaterial(
                request_id=request_id,
                documents=[
                    {
                        "document_id": document_id,
                        "source_id": source_id,
                        "request_id": request_id,
                        "file_name": "cities.csv",
                        "mime_type": "text/csv",
                        "storage_ref": storage_ref,
                    }
                ],
                datasets=[
                    {
                        "dataset_id": dataset_id,
                        "request_id": request_id,
                        "name": "cities.csv",
                        "row_count": 1,
                        "storage_ref": storage_ref,
                        "dataset_schema": {"city": "string"},
                    }
                ],
                units=[to_delivery_unit(unit, request_id)],
            )

        monkeypatch.setattr(runner_module, "load_request_material", _load)

    async def test_the_ingest_step_is_not_dropped(
        self,
        ingested_file: None,
        web_doubles: dict[str, AsyncMock],
        captured_steps: list[dict[str, Any]],
        mock_llm: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Orienter le plan sur la base ne doit pas jeter le fichier fourni."""
        _use_engine(monkeypatch, FakeEngine(ROWS))

        await _run("data", {"source_preferences": [PREFERENCE]})

        actions = [step["action"] for step in captured_steps]
        # §17.1 — la mémoire ouvre le plan (lot L4) ; les deux matières possédées
        # (fichier et base) restent présentes, quel que soit leur ordre interne.
        assert actions[0] == "memory_lookup"
        assert "file_ingest" in actions
        assert "query_database" in actions

    async def test_both_datasets_are_delivered(
        self,
        ingested_file: None,
        web_doubles: dict[str, AsyncMock],
        mock_llm: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _use_engine(monkeypatch, FakeEngine(ROWS))

        delivery = await _run("data", {"source_preferences": [PREFERENCE]})

        storage_refs = {dataset["storage_ref"] for dataset in delivery["datasets"]}
        assert storage_refs == {STORAGE_REF, "s3://inis-artifacts/documents/cities.csv"}

    async def test_no_web_search_is_launched(
        self,
        ingested_file: None,
        web_doubles: dict[str, AsyncMock],
        mock_llm: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _use_engine(monkeypatch, FakeEngine(ROWS))

        await _run("data", {"source_preferences": [PREFERENCE]})

        assert web_doubles["search"].await_count == 0


class TestTheDatasetStaysConsultable:
    """§11/§27 — un ``DATA_`` livré doit exister : sinon la livraison le dit."""

    async def test_without_a_database_the_gap_is_named(
        self,
        web_doubles: dict[str, AsyncMock],
        mock_llm: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _use_engine(monkeypatch, FakeEngine(ROWS))
        monkeypatch.delenv("INIS_DATABASE_URL", raising=False)

        delivery = await _run("data", {"source_preferences": [PREFERENCE]})

        assert len(delivery["datasets"]) == 1
        assert any("non persisté" in text for text in delivery["limitations"])

    async def test_a_failed_read_says_nothing_about_persistence(
        self,
        web_doubles: dict[str, AsyncMock],
        mock_llm: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Sans dataset, il n'y a rien à persister : la livraison n'en parle pas."""
        _use_engine(monkeypatch, FailingEngine())
        monkeypatch.delenv("INIS_DATABASE_URL", raising=False)

        delivery = await _run("data", {"source_preferences": [PREFERENCE]})

        assert not any("non persisté" in text for text in delivery["limitations"])


class TestTheOtherRequestTypesKeepTheirPlan:
    """§7 — seul « data »/« source » remplace l'acquisition par la source nommée."""

    async def test_a_research_request_still_searches_the_web(
        self,
        web_doubles: dict[str, AsyncMock],
        mock_llm: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _use_engine(monkeypatch, FakeEngine(ROWS))

        delivery = await _run("research", {"source_preferences": [PREFERENCE]})

        assert web_doubles["search"].await_count >= 1
        assert delivery["provenance"]["request_type"] == "research"

    async def test_a_research_request_also_delivers_its_rows(
        self,
        web_doubles: dict[str, AsyncMock],
        mock_llm: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """La base nommée n'est pas ignorée parce que la demande n'est pas « data »."""
        _use_engine(monkeypatch, FakeEngine(ROWS))

        delivery = await _run("research", {"source_preferences": [PREFERENCE]})

        assert len(delivery["datasets"]) == 1
        assert len(_db_units(delivery)) == 2

    async def test_the_read_comes_first(
        self,
        web_doubles: dict[str, AsyncMock],
        captured_steps: list[dict[str, Any]],
        mock_llm: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """La préférence nommée par le client est lue avant l'acquisition web."""
        _use_engine(monkeypatch, FakeEngine(ROWS))

        await _run("research", {"source_preferences": [PREFERENCE]})

        # §17.1 — la lecture de la base reste le premier pas **d'acquisition** :
        # seule l'étape de mémoire la précède désormais (lot L4).
        assert captured_steps[0]["action"] == "memory_lookup"
        assert captured_steps[1]["action"] == "query_database"

    async def test_a_request_without_preference_is_not_touched(
        self,
        web_doubles: dict[str, AsyncMock],
        captured_steps: list[dict[str, Any]],
        mock_llm: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Aucune préférence PostgreSQL : le plan reste celui de la recherche (§8.4)."""
        _use_engine(monkeypatch, FakeEngine(ROWS))

        delivery = await _run("research")

        assert all(step["action"] != "query_database" for step in captured_steps)
        assert delivery["datasets"] == []

    async def test_a_data_request_without_preference_is_not_noised(
        self,
        web_doubles: dict[str, AsyncMock],
        mock_llm: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Une demande « data » sans base nommée ne parle pas de PostgreSQL."""
        _use_engine(monkeypatch, FakeEngine(ROWS))

        delivery = await _run("data")

        assert not any("query_database" in text for text in delivery["limitations"])

    async def test_the_delivery_states_the_request_type_it_planned_for(
        self,
        web_doubles: dict[str, AsyncMock],
        mock_llm: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _use_engine(monkeypatch, FakeEngine(ROWS))

        delivery = await _run("data", {"source_preferences": [PREFERENCE]})

        assert delivery["provenance"]["request_type"] == "data"