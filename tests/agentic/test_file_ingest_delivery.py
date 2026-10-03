"""§7/§8.4/§24.1 — un ``file_ingest`` réel remplit le colis de la requête.

Le fichier téléversé est ingéré à l'arrivée (L2.3) : ses unités §11 et son
``Dataset`` sont en base avant que la requête ne tourne. Ce fichier verrouille le
câblage qui les fait entrer dans la livraison — ``datasets[]`` non vide, unités
localisables, transformations §12.1 de l'ingestion — **et** le fait que
``request_type`` oriente enfin le plan (§7, C4) :

* ``data`` : le fichier est la source, aucune recherche web n'est lancée ;
* ``research`` : le plan garde ses étapes web et gagne l'ingestion du fichier.

La matière est doublée ici (pas de PostgreSQL) : le chemin réel est couvert par
``tests/integration/test_request_file_ingestion_e2e.py``.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.api.v1.requests import pipeline_runner as runner_module
from app.api.v1.requests.pipeline_runner import PipelineRunner
from app.domain.value_objects.ulid import ULID
from app.knowledge.ingestion.request_material import RequestMaterial, to_delivery_unit

OBJECTIVE = "Analyse la population des villes du fichier fourni"
DOCUMENT_ID = "DOC_01M3Q0000000000000000000AA"
DATASET_ID = "DATA_01M3Q0000000000000000000AA"
SOURCE_ID = "SRC_01M3Q0000000000000000000AA"
STORAGE_REF = "s3://inis-artifacts/documents/REQ_1/abc.csv"

DOCUMENT = {
    "document_id": DOCUMENT_ID,
    "source_id": SOURCE_ID,
    "request_id": "REQ_PLACEHOLDER",
    "file_name": "villes.csv",
    "mime_type": "text/csv",
    "size_bytes": 41,
    "storage_ref": STORAGE_REF,
}
DATASET = {
    "dataset_id": DATASET_ID,
    "request_id": "REQ_PLACEHOLDER",
    "name": "villes.csv",
    "row_count": 2,
    "storage_ref": STORAGE_REF,
    "schema": {"city": "string", "population": "string"},
}
UNITS = [
    {
        "information_id": "INF_01M3Q0000000000000000000BB",
        "type": "record",
        "content": {"values": {"city": "Paris", "population": "2145906"}},
        "raw_reference": {"document_id": DOCUMENT_ID, "storage_ref": STORAGE_REF},
        "source_id": SOURCE_ID,
        "document_id": DOCUMENT_ID,
        "dataset_id": DATASET_ID,
        "location": {"kind": "row", "row": 1, "columns": ["city", "population"]},
        "context": {"origin": "uploaded_document"},
        "provenance": {"extracted_from": STORAGE_REF, "method": "read_csv"},
        "data_stage": "raw",
        "epistemic_status": "factual",
    },
    {
        "information_id": "INF_01M3Q0000000000000000000BC",
        "type": "record",
        "content": {"values": {"city": "Berlin", "population": "3645000"}},
        "raw_reference": {"document_id": DOCUMENT_ID, "storage_ref": STORAGE_REF},
        "source_id": SOURCE_ID,
        "document_id": DOCUMENT_ID,
        "dataset_id": DATASET_ID,
        "location": {"kind": "row", "row": 2, "columns": ["city", "population"]},
        "context": {"origin": "uploaded_document"},
        "provenance": {"extracted_from": STORAGE_REF, "method": "read_csv"},
        "data_stage": "raw",
        "epistemic_status": "factual",
    },
]
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


@pytest.fixture
def ingested(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace the material loader: this request ingested one CSV."""

    async def _load(request_id: str, **kwargs: Any) -> RequestMaterial:
        return RequestMaterial(
            request_id=request_id,
            documents=[{**DOCUMENT, "request_id": request_id}],
            datasets=[{**DATASET, "request_id": request_id}],
            units=[to_delivery_unit(unit, request_id) for unit in UNITS],
        )

    monkeypatch.setattr(runner_module, "load_request_material", _load)


async def _run(request_type: str = "data") -> dict[str, Any]:
    """Run the pipeline for one request of *request_type*."""
    return await PipelineRunner().run(
        ULID.new("REQ_"), {"objective": OBJECTIVE, "request_type": request_type}
    )


def _units(delivery: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the delivered units that carry the ingested rows."""
    return [
        unit
        for unit in delivery["information_units"]
        if unit.get("document_id") == DOCUMENT_ID
    ]


def _stages(delivery: dict[str, Any]) -> list[tuple[str, str]]:
    """Return the (stage, tool) pairs of the delivered §12.1 transformations."""
    return [
        (item["parameters"]["stage"], item["tool"])
        for item in delivery["transformations"]
    ]

class TestADataRequestIsPlannedAroundItsFile:
    """§7 — « data » veut dire : la source, c'est le fichier fourni."""

    async def test_the_datasets_of_the_request_are_delivered(
        self, ingested: None, web_doubles: dict[str, AsyncMock], mock_llm: Any
    ) -> None:
        delivery = await _run("data")

        assert [dataset["dataset_id"] for dataset in delivery["datasets"]] == [
            DATASET_ID
        ]
        assert delivery["datasets"][0]["row_count"] == 2
        assert delivery["datasets"][0]["storage_ref"] == STORAGE_REF

    async def test_the_file_units_are_delivered_and_locatable(
        self, ingested: None, web_doubles: dict[str, AsyncMock], mock_llm: Any
    ) -> None:
        """§11 — une unité livrée dit où elle se trouve dans le document."""
        delivery = await _run("data")

        units = _units(delivery)
        assert {unit["information_id"] for unit in units} == {
            "INF_01M3Q0000000000000000000BB",
            "INF_01M3Q0000000000000000000BC",
        }
        for unit in units:
            assert unit["location"]["kind"] == "row"
            assert unit["location"]["row"] in (1, 2)
            assert unit["dataset_id"] == DATASET_ID
            assert unit["provenance"]["extracted_from"] == STORAGE_REF

    async def test_the_document_is_delivered_as_a_source(
        self, ingested: None, web_doubles: dict[str, AsyncMock], mock_llm: Any
    ) -> None:
        """§9.1 — le document est une source du colis, pas un identifiant flottant."""
        delivery = await _run("data")

        sources = {source["source_id"]: source for source in delivery["sources"]}
        assert SOURCE_ID in sources
        assert sources[SOURCE_ID]["source_type"] == "file"
        assert sources[SOURCE_ID]["url"] == STORAGE_REF
        assert sources[SOURCE_ID]["name"] == "villes.csv"

    async def test_no_web_search_is_launched(
        self, ingested: None, web_doubles: dict[str, AsyncMock], mock_llm: Any
    ) -> None:
        """§7/§8.4 — le planificateur ne cherche pas sur le web ce qu'on lui donne."""
        await _run("data")

        assert web_doubles["search"].await_count == 0
        assert web_doubles["extract"].await_count == 0

    async def test_the_file_ingest_step_is_done_and_names_what_it_read(
        self,
        ingested: None,
        web_doubles: dict[str, AsyncMock],
        captured_steps: list[dict[str, Any]],
        mock_llm: Any,
    ) -> None:
        """§8.4 — l'étape est `done` et son output compte ce qui a été relu."""
        await _run("data")

        ingest = [
            step for step in captured_steps if step["action"] == "file_ingest"
        ]
        assert ingest, "le plan doit contenir l'étape d'ingestion du fichier"
        assert ingest[0]["status"] == "done"
        assert "villes.csv" in ingest[0]["output"]
        assert ingest[0]["documents"][0]["document_id"] == DOCUMENT_ID
        assert ingest[0]["datasets"] == [DATASET_ID]
        assert ingest[0]["tools_required"]

    async def test_the_lineage_names_the_reader_that_ran(
        self, ingested: None, web_doubles: dict[str, AsyncMock], mock_llm: Any
    ) -> None:
        """§12.1 — l'étage `raw` du fichier porte le lecteur qui l'a lu."""
        delivery = await _run("data")

        stages = _stages(delivery)
        assert ("raw", "read_csv") in stages
        assert ("normalized", "DocumentIngestor.ingest") in stages

    async def test_the_extraction_stage_is_not_claimed_by_the_web_path(
        self, ingested: None, web_doubles: dict[str, AsyncMock], mock_llm: Any
    ) -> None:
        delivery = await _run("data")

        tools = [tool for _, tool in _stages(delivery)]
        assert "FactExtractor.extract" not in tools

    async def test_the_delivery_states_the_request_type_it_planned_for(
        self, ingested: None, web_doubles: dict[str, AsyncMock], mock_llm: Any
    ) -> None:
        delivery = await _run("data")

        assert delivery["provenance"]["request_type"] == "data"

class TestTheOtherRequestTypesKeepTheirPlan:
    """§7 — seul « data »/« source » remplace l'acquisition par le fichier."""

    async def test_a_research_request_still_searches_the_web(
        self, ingested: None, web_doubles: dict[str, AsyncMock], mock_llm: Any
    ) -> None:
        delivery = await _run("research")

        assert web_doubles["search"].await_count >= 1
        assert delivery["provenance"]["request_type"] == "research"

    async def test_a_research_request_also_delivers_its_file(
        self, ingested: None, web_doubles: dict[str, AsyncMock], mock_llm: Any
    ) -> None:
        """Le fichier ingéré n'est pas ignoré parce que la demande n'est pas « data »."""
        delivery = await _run("research")

        assert [dataset["dataset_id"] for dataset in delivery["datasets"]] == [
            DATASET_ID
        ]
        assert {unit["information_id"] for unit in _units(delivery)} == {
            "INF_01M3Q0000000000000000000BB",
            "INF_01M3Q0000000000000000000BC",
        }

    async def test_the_ingest_step_comes_first(
        self,
        ingested: None,
        web_doubles: dict[str, AsyncMock],
        captured_steps: list[dict[str, Any]],
        mock_llm: Any,
    ) -> None:
        await _run("research")

        actions = [step["action"] for step in captured_steps]
        # §17.1 — la mémoire ouvre le plan (lot L4) ; le pas de fichier suit.
        assert actions[:2] == ["memory_lookup", "file_ingest"]
        assert "collect_information" in actions


class TestADataRequestWithoutIngestedFile:
    """§0.2 — rien n'est inventé quand il n'y a rien à relire."""

    async def test_no_ingest_step_is_added_without_material(
        self,
        web_doubles: dict[str, AsyncMock],
        captured_steps: list[dict[str, Any]],
        mock_llm: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("INIS_DATABASE_URL", raising=False)

        delivery = await _run("data")

        assert all(step["action"] != "file_ingest" for step in captured_steps)
        assert delivery["datasets"] == []

    async def test_the_delivery_says_why_the_file_cannot_be_read(
        self,
        web_doubles: dict[str, AsyncMock],
        captured_steps: list[dict[str, Any]],
        mock_llm: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """§25.2 — un colis « data » sans matière explique l'absence."""
        monkeypatch.delenv("INIS_DATABASE_URL", raising=False)

        delivery = await _run("data")

        assert any("INIS_DATABASE_URL" in text for text in delivery["limitations"])

    async def test_a_research_request_without_material_is_not_noised(
        self,
        web_doubles: dict[str, AsyncMock],
        captured_steps: list[dict[str, Any]],
        mock_llm: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Une demande « research » sans fichier ne parle pas d'ingestion."""
        monkeypatch.delenv("INIS_DATABASE_URL", raising=False)

        delivery = await _run("research")

        assert not any("INIS_DATABASE_URL" in text for text in delivery["limitations"])

