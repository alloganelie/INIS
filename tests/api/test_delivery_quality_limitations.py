"""L5 exit criterion — the defects of an ingested CSV reach the colis.

The plan states it as a criterion, not as a wish: *a CSV containing duplicates,
missing values and an inconsistency must produce a delivery where those three
defects are explicitly listed*. This test runs the real pipeline with a request
whose file was ingested (the material loader is replaced, as in
``tests/agentic/test_file_ingest_delivery.py``) and reads the colis.

What is asserted, in the delivery's own words:

* ``datasets[].quality_score`` is not ``None`` — the §13.2 controls ran;
* the three defects appear in ``limitations`` (§24.1, §37 « signaler > inventer »);
* the per-dataset ``quality`` block carries the checks and their sub-scores;
* a dataset whose rows are absent from the colis reports ``quality_score: None``
  and says why, instead of scoring an empty set.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.api.v1.requests import pipeline_runner as runner_module
from app.api.v1.requests.pipeline_runner import PipelineRunner
from app.domain.value_objects.ulid import ULID
from app.knowledge.ingestion.request_material import RequestMaterial, to_delivery_unit

OBJECTIVE = "Qualité du fichier de population fourni"
DATASET_ID = "DATA_01M3Q0000000000000000000QL"
SOURCE_ID = "SRC_01M3Q0000000000000000000QL"
DOCUMENT_ID = "DOC_01M3Q0000000000000000000QL"
STORAGE_REF = "s3://inis-artifacts/documents/REQ_QL/villes.csv"

#: The plan's exit criterion: a duplicate, a missing value, an inconsistent column.
DIRTY_ROWS = [
    {"ville": "Paris", "population": 2148000},
    {"ville": "Lyon", "population": 522250},
    {"ville": "Lyon", "population": 522250},
    {"ville": "Marseille", "population": None},
    {"ville": "Nice", "population": "342 522"},
]

CLEAN_ROWS = [
    {"ville": "Paris", "population": 2148000},
    {"ville": "Lyon", "population": 522250},
]


def _material(rows: list[dict[str, Any]]):
    """Return a material loader whose file holds *rows* (real unit shape)."""

    async def _load(request_id: str, **kwargs: Any) -> RequestMaterial:
        units = [
            to_delivery_unit(
                {
                    "information_id": f"INF_QL_{index}",
                    "type": "record",
                    "content": {"values": row, "text": " | ".join(map(str, row.values()))},
                    "raw_reference": {"document_id": DOCUMENT_ID, "storage_ref": STORAGE_REF},
                    "source_id": SOURCE_ID,
                    "document_id": DOCUMENT_ID,
                    "dataset_id": DATASET_ID,
                    "location": {"kind": "row", "row": index + 1},
                    "provenance": {"method": "read_csv"},
                    "data_stage": "raw",
                },
                request_id,
            )
            for index, row in enumerate(rows)
        ]
        return RequestMaterial(
            request_id=request_id,
            documents=[
                {
                    "document_id": DOCUMENT_ID,
                    "source_id": SOURCE_ID,
                    "request_id": request_id,
                    "file_name": "villes.csv",
                    "mime_type": "text/csv",
                    "storage_ref": STORAGE_REF,
                }
            ],
            datasets=[
                {
                    "dataset_id": DATASET_ID,
                    "request_id": request_id,
                    "name": "villes.csv",
                    "row_count": len(rows),
                    "storage_ref": STORAGE_REF,
                    "schema": {},
                }
            ],
            units=units,
        )

    return _load


@pytest.fixture
def no_persistence(monkeypatch: pytest.MonkeyPatch) -> None:
    """Deliver without a database: the quality checks need no PostgreSQL."""

    async def _fake_persist(**kwargs: Any) -> tuple[bool, list[str], dict[str, Any]]:
        return (
            False,
            ["persistence: in-memory only (test)"],
            {"audit_event_id": ULID.new("AUD_"), "timestamp": "2026-01-01T00:00:00Z"},
        )

    monkeypatch.setattr(
        "app.api.v1.requests.pipeline_runner.persist_pipeline_delivery", _fake_persist
    )


@pytest.fixture
def no_web(monkeypatch: pytest.MonkeyPatch) -> None:
    """No web acquisition: the delivered dataset is the only material."""
    from unittest.mock import AsyncMock

    monkeypatch.setattr(
        "app.connectors.web.provider_router.ProviderRouter.search", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(
        "app.connectors.web.extractors.wikipedia_extractor.WikipediaExtractor.extract",
        AsyncMock(return_value={}),
    )


async def _run() -> dict[str, Any]:
    """Run the pipeline for one ``data`` request."""
    return await PipelineRunner().run(
        ULID.new("REQ_"), {"objective": OBJECTIVE, "request_type": "data"}
    )


class TestTheThreeDefectsAreListed:
    """The criterion, defect by defect, read from the colis itself."""

    @pytest.mark.asyncio
    async def test_quality_score_is_measured(
        self, monkeypatch: pytest.MonkeyPatch, no_persistence: None, no_web: None
    ) -> None:
        monkeypatch.setattr(runner_module, "load_request_material", _material(DIRTY_ROWS))
        delivery = await _run()

        dataset = next(item for item in delivery["datasets"] if item["dataset_id"] == DATASET_ID)
        assert dataset["quality_score"] is not None
        assert 0.0 <= dataset["quality_score"] <= 1.0

        block = delivery["quality"]["datasets"][DATASET_ID]
        assert block["rows_examined"] == len(DIRTY_ROWS)
        assert set(block["checks"]) == {"completeness", "uniqueness", "consistency"}

    @pytest.mark.asyncio
    async def test_limitations_name_the_three_defects(
        self, monkeypatch: pytest.MonkeyPatch, no_persistence: None, no_web: None
    ) -> None:
        monkeypatch.setattr(runner_module, "load_request_material", _material(DIRTY_ROWS))
        delivery = await _run()

        limitations = " | ".join(delivery["limitations"])
        assert "population" in limitations, "la valeur manquante doit être nommée"
        assert "doublon" in limitations, "le doublon doit être nommé"
        assert "mixes types" in limitations, "l'incohérence de colonne doit être nommée"
        assert DATASET_ID in limitations


class TestHonestyOfTheScore:
    """A score exists only where the controls could run (§13.3, §37)."""

    @pytest.mark.asyncio
    async def test_a_clean_dataset_adds_no_quality_limitation(
        self, monkeypatch: pytest.MonkeyPatch, no_persistence: None, no_web: None
    ) -> None:
        monkeypatch.setattr(runner_module, "load_request_material", _material(CLEAN_ROWS))
        delivery = await _run()

        dataset = next(item for item in delivery["datasets"] if item["dataset_id"] == DATASET_ID)
        assert dataset["quality_score"] == pytest.approx(1.0)
        assert "doublon" not in " | ".join(delivery["limitations"])

    @pytest.mark.asyncio
    async def test_a_schema_only_dataset_is_not_scored(
        self, monkeypatch: pytest.MonkeyPatch, no_persistence: None, no_web: None
    ) -> None:
        """No rows in the colis ⇒ ``None`` and a stated reason, never a fake score."""
        material = _material(CLEAN_ROWS)

        async def _load_without_units(request_id: str, **kwargs: Any) -> RequestMaterial:
            loaded = await material(request_id, **kwargs)
            return RequestMaterial(
                request_id=loaded.request_id,
                documents=loaded.documents,
                datasets=loaded.datasets,
                units=[],
                limitations=loaded.limitations,
            )

        monkeypatch.setattr(runner_module, "load_request_material", _load_without_units)
        delivery = await _run()

        dataset = next(item for item in delivery["datasets"] if item["dataset_id"] == DATASET_ID)
        assert dataset["quality_score"] is None
        assert any("non mesurée" in limitation for limitation in delivery["limitations"])
        assert any(
            DATASET_ID in item for item in delivery.get("missing_information", [])
        ), "une qualité non mesurée est une information manquante (§13.3)"
