"""§12 — the colis says which stage every piece of material really reached.

A delivery that only lists ``information_units`` and ``evidence`` leaves the
client to guess how far the data went: was this row read? enriched? synthesised
by the run? L3.1 closes that gap by exposing the §12 progression at the three
places it exists:

* ``information_units[].data_stage`` — the stage of the unit itself, in the four
  values of :data:`app.core.constants.DATA_STAGES`;
* ``datasets[].data_stage`` — the furthest stage reached by the units read out of
  each dataset;
* ``transformations[]`` — one row per stage that ran, with the ``enriched`` stage
  naming **both** its producers: ``Enricher.enrich`` (notation) and the synthesis
  (findings). A stage that produced nothing stays absent.

No PostgreSQL, no network: the ingested material is doubled and the web providers
are silenced, as in ``tests/agentic/test_file_ingest_delivery.py``.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.api.v1.requests import pipeline_runner as runner_module
from app.api.v1.requests.pipeline_runner import PipelineRunner
from app.core.constants import DATA_STAGES
from app.domain.value_objects.ulid import ULID
from app.knowledge.ingestion.request_material import RequestMaterial, to_delivery_unit

OBJECTIVE = "Analyse les livraisons du fichier fourni"
DOCUMENT_ID = "DOC_01M3Q0000000000000000000AA"
DATASET_ID = "DATA_01M3Q0000000000000000000AA"
SOURCE_ID = "SRC_01M3Q0000000000000000000AA"
STORAGE_REF = "s3://inis-artifacts/documents/REQ_1/livraisons.csv"
DATED_UNIT_ID = "INF_01M3Q0000000000000000000BB"
PLAIN_UNIT_ID = "INF_01M3Q0000000000000000000BC"

#: §41.3 — the request asks for French conventions, so ``15/01/2024`` is read
#: day-first: the locale is configuration, never a guess.
CONTEXT = {"normalization_locale": "fr-FR"}

DOCUMENT = {
    "document_id": DOCUMENT_ID,
    "source_id": SOURCE_ID,
    "request_id": "REQ_PLACEHOLDER",
    "file_name": "livraisons.csv",
    "mime_type": "text/csv",
    "size_bytes": 41,
    "storage_ref": STORAGE_REF,
}
DATASET = {
    "dataset_id": DATASET_ID,
    "request_id": "REQ_PLACEHOLDER",
    "name": "livraisons.csv",
    "row_count": 2,
    "storage_ref": STORAGE_REF,
    "dataset_schema": {"livraison": "string"},
}


def _unit(information_id: str, values: dict[str, str], row: int) -> dict[str, Any]:
    """Return one stored ``record`` unit of the ingested CSV, at stage §12."""
    return {
        "information_id": information_id,
        "type": "record",
        "content": {"values": values},
        "raw_reference": {"document_id": DOCUMENT_ID, "storage_ref": STORAGE_REF},
        "source_id": SOURCE_ID,
        "document_id": DOCUMENT_ID,
        "dataset_id": DATASET_ID,
        "location": {"kind": "row", "row": row, "columns": sorted(values)},
        "context": {"origin": "uploaded_document"},
        "provenance": {"extracted_from": STORAGE_REF, "method": "read_csv"},
        # L2.3 stores what the reader produced: the §12 stage of that step.
        "data_stage": "normalized",
        "epistemic_status": "factual",
    }


#: A row whose notation can be normalised (a French date)…
DATED_UNIT = _unit(DATED_UNIT_ID, {"city": "Paris", "livraison": "15/01/2024"}, 1)
#: …and a row with nothing to normalise, which must keep stating its gap.
PLAIN_UNIT = _unit(PLAIN_UNIT_ID, {"city": "Berlin"}, 2)


@pytest.fixture
def web_doubles(monkeypatch: pytest.MonkeyPatch) -> dict[str, AsyncMock]:
    """Silence the §9/§10 providers: nothing of this delivery comes from the web."""
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
def ingested(monkeypatch: pytest.MonkeyPatch):
    """Return an installer doubling the §9.1 material read back for the request."""

    def _install(units: list[dict[str, Any]]) -> None:
        async def _load(request_id: str, **kwargs: Any) -> RequestMaterial:
            return RequestMaterial(
                request_id=request_id,
                documents=[{**DOCUMENT, "request_id": request_id}],
                datasets=[{**DATASET, "request_id": request_id}],
                units=[to_delivery_unit(unit, request_id) for unit in units],
            )

        monkeypatch.setattr(runner_module, "load_request_material", _load)

    return _install


@pytest.fixture
def sqlite_less_persistence(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the delivery in memory: this test is about its shape, not its storage."""

    async def _fake_persist(**kwargs: Any) -> tuple[bool, list[str], dict[str, Any]]:
        return False, [], {
            "audit_event_id": ULID.new("AUD_"),
            "timestamp": "2026-01-01T00:00:00Z",
        }

    monkeypatch.setattr(
        "app.api.v1.requests.pipeline_runner.persist_pipeline_delivery", _fake_persist
    )


async def _run() -> dict[str, Any]:
    """Run the pipeline for one ``data`` request over the ingested material."""
    return await PipelineRunner().run(
        ULID.new("REQ_"),
        {"objective": OBJECTIVE, "request_type": "data", "context": dict(CONTEXT)},
    )


def _units_by_id(delivery: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return the delivered units indexed by identifier."""
    return {
        str(unit.get("information_id")): unit for unit in delivery["information_units"]
    }


def _enricher_rows(delivery: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the §12.1 ``enriched`` rows the enricher produced."""
    return [
        item
        for item in delivery["transformations"]
        if item["parameters"]["stage"] == "enriched" and item["tool"] == "Enricher.enrich"
    ]


class TestAUnitSaysWhichStageItReached:
    """§12 — the delivered unit carries the stage of the chain it walked."""

    async def test_every_delivered_unit_uses_the_four_stages(
        self,
        ingested: Any,
        web_doubles: dict[str, AsyncMock],
        sqlite_less_persistence: None,
        mock_llm: Any,
    ) -> None:
        ingested([DATED_UNIT, PLAIN_UNIT])

        delivery = await _run()

        stages = {str(unit.get("data_stage")) for unit in delivery["information_units"]}
        assert stages
        assert stages <= set(DATA_STAGES)

    async def test_the_dated_row_is_enriched_and_says_so(
        self,
        ingested: Any,
        web_doubles: dict[str, AsyncMock],
        sqlite_less_persistence: None,
        mock_llm: Any,
    ) -> None:
        ingested([DATED_UNIT, PLAIN_UNIT])

        delivery = await _run()
        unit = _units_by_id(delivery)[DATED_UNIT_ID]

        assert unit["data_stage"] == "enriched"
        block = unit["context"]["enrichment"]
        assert block["data_stage"] == "enriched"
        assert block["method"] == "Enricher.normalize"
        assert [value["value"]["iso"] for value in block["values"]] == ["2024-01-15"]

    async def test_the_row_with_nothing_to_read_stays_normalized(
        self,
        ingested: Any,
        web_doubles: dict[str, AsyncMock],
        sqlite_less_persistence: None,
        mock_llm: Any,
    ) -> None:
        """A stage that was not reached is not claimed (§0.2)."""
        ingested([DATED_UNIT, PLAIN_UNIT])

        delivery = await _run()
        unit = _units_by_id(delivery)[PLAIN_UNIT_ID]

        assert unit["data_stage"] == "normalized"
        assert unit["context"].get("enrichment") is None


class TestADatasetExposesTheStageOfItsRows:
    """§12 — a table says how far its own material went."""

    async def test_a_dataset_whose_rows_were_enriched_is_enriched(
        self,
        ingested: Any,
        web_doubles: dict[str, AsyncMock],
        sqlite_less_persistence: None,
        mock_llm: Any,
    ) -> None:
        ingested([DATED_UNIT, PLAIN_UNIT])

        delivery = await _run()
        dataset = delivery["datasets"][0]

        assert dataset["dataset_id"] == DATASET_ID
        assert dataset["data_stage"] == "enriched"
        assert dataset["data_stage"] in DATA_STAGES

    async def test_a_dataset_whose_rows_stayed_normalized_is_normalized(
        self,
        ingested: Any,
        web_doubles: dict[str, AsyncMock],
        sqlite_less_persistence: None,
        mock_llm: Any,
    ) -> None:
        ingested([PLAIN_UNIT])

        delivery = await _run()

        assert delivery["datasets"][0]["data_stage"] == "normalized"


class TestTheLineageExposesTheProgression:
    """§12.1 — one row per stage that ran, and two producers for « enriched »."""

    async def test_the_enriched_step_has_its_own_row_and_its_own_ids(
        self,
        ingested: Any,
        web_doubles: dict[str, AsyncMock],
        sqlite_less_persistence: None,
        mock_llm: Any,
    ) -> None:
        ingested([DATED_UNIT, PLAIN_UNIT])

        delivery = await _run()
        rows = _enricher_rows(delivery)

        assert len(rows) == 1
        assert rows[0]["output_ids"] == [DATED_UNIT_ID]
        assert PLAIN_UNIT_ID not in rows[0]["output_ids"]
        assert rows[0]["parameters"]["values"] == 1
        assert rows[0]["parameters"]["locale"] == "fr-FR"

    async def test_the_synthesis_is_not_credited_with_the_enrichment(
        self,
        ingested: Any,
        web_doubles: dict[str, AsyncMock],
        sqlite_less_persistence: None,
        mock_llm: Any,
    ) -> None:
        ingested([DATED_UNIT, PLAIN_UNIT])

        delivery = await _run()
        enriched_rows = [
            item
            for item in delivery["transformations"]
            if item["parameters"]["stage"] == "enriched"
        ]

        assert {row["operator"] for row in enriched_rows} == {"Enricher", "ModelRouter"}
        assert len(enriched_rows) == 2

    async def test_the_stages_of_the_lineage_are_the_ones_of_the_spec(
        self,
        ingested: Any,
        web_doubles: dict[str, AsyncMock],
        sqlite_less_persistence: None,
        mock_llm: Any,
    ) -> None:
        ingested([DATED_UNIT, PLAIN_UNIT])

        delivery = await _run()
        stages = [item["parameters"]["stage"] for item in delivery["transformations"]]

        assert set(stages) <= set(DATA_STAGES)
        assert stages[0] == "raw"
        # This run delivers no artifact, so the « derived » stage is absent
        # instead of being recorded as a stage that happened (§0.2).
        assert delivery["artifacts"] == []
        assert "derived" not in stages
        assert "enriched" in stages

    async def test_a_run_that_enriched_nothing_records_no_enriched_step(
        self,
        ingested: Any,
        web_doubles: dict[str, AsyncMock],
        sqlite_less_persistence: None,
        mock_llm: Any,
    ) -> None:
        """§0.2 — a stage with no output is absent, never recorded as a fact."""
        ingested([PLAIN_UNIT])

        delivery = await _run()

        assert _enricher_rows(delivery) == []

    async def test_the_limitation_of_the_enrichment_is_delivered(
        self,
        ingested: Any,
        web_doubles: dict[str, AsyncMock],
        sqlite_less_persistence: None,
        mock_llm: Any,
    ) -> None:
        """The gap the enricher could not close is stated in the colis (§25.2)."""
        ingested(
            [
                _unit(
                    DATED_UNIT_ID,
                    {"city": "Paris", "livraison": "15/01/2024", "budget": "$500"},
                    1,
                )
            ]
        )

        delivery = await _run()

        assert any("devise" in line for line in delivery["limitations"])
