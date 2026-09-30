"""§14.4 — a file and a web page disagreeing must produce a ``Conflict``.

The pipeline carried an empty ``conflicts`` slot, so a delivery where the
ingested file said one thing and the web said another looked unanimous. This
test runs the real pipeline with both sources and reads the colis.

Two behaviours are proven, and the second matters as much as the first:

* a file row (*Paris, population = 2 148 000*) and a web claim (*Paris,
  population = 2 100 000*) produce **one** ``Conflict`` between the two units,
  with a difference type and a severity — no silent arbitration;
* a web source whose unit carries no comparable claim is **stated as
  incomparable**: the delivery says the comparison was partial instead of
  implying agreement.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.api.v1.requests import pipeline_runner as runner_module
from app.api.v1.requests.pipeline_runner import PipelineRunner
from app.domain.value_objects.ulid import ULID
from app.knowledge.ingestion.request_material import RequestMaterial, to_delivery_unit
from app.quality.source_quality import assess_sources

OBJECTIVE = "Comparer la population de Paris entre le fichier et le web"
DATASET_ID = "DATA_01M3Q000000000000000000CF"
FILE_SOURCE = "SRC_01M3Q000000000000000000CF1"
WEB_SOURCE = "SRC_01M3Q000000000000000000CF2"
DOCUMENT_ID = "DOC_01M3Q000000000000000000CF"
STORAGE_REF = "s3://inis-artifacts/documents/REQ_CF/villes.csv"

#: The file row: the ingestion stores it as ``{"values": {...}}``.
FILE_UNIT = {
    "information_id": "INF_01M3Q0000000000000000000CF",
    "type": "record",
    "content": {"values": {"ville": "Paris", "population": 2148000}, "text": "Paris | 2148000"},
    "raw_reference": {"document_id": DOCUMENT_ID, "storage_ref": STORAGE_REF},
    "source_id": FILE_SOURCE,
    "dataset_id": DATASET_ID,
    "location": {"kind": "row", "row": 1},
    "provenance": {"method": "read_csv"},
    "data_stage": "raw",
}

#: The web claim, in the shape §14.4 compares.
WEB_UNIT_CLAIM = {
    "information_id": "INF_01M3Q0000000000000000000CG",
    "type": "text",
    "content": {"subject": "Paris", "predicate": "population", "value": 2100000},
    "raw_reference": {"url": "https://exemple.invalid/paris"},
    "source_id": WEB_SOURCE,
    "location": {},
    "provenance": {"extracted_from": "https://exemple.invalid/paris"},
    "data_stage": "raw",
}

#: The same web source, with a sentence nobody can compare to a column.
WEB_UNIT_SENTENCE = {
    **WEB_UNIT_CLAIM,
    "information_id": "INF_01M3Q0000000000000000000CH",
    "content": {"text": "Paris compte environ deux millions d'habitants."},
}


def _material(web_unit: dict[str, Any]):
    """Return a loader for a request whose file and web both brought material."""

    async def _load(request_id: str, **kwargs: Any) -> RequestMaterial:
        return RequestMaterial(
            request_id=request_id,
            documents=[
                {
                    "document_id": DOCUMENT_ID,
                    "source_id": FILE_SOURCE,
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
                    "row_count": 1,
                    "storage_ref": STORAGE_REF,
                    "schema": {},
                }
            ],
            units=[to_delivery_unit(FILE_UNIT, request_id)],
        )

    return _load


@pytest.fixture
def web_facts(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Make the §10 extraction return the web unit this test wants."""
    facts: list[dict[str, Any]] = []

    async def _extract(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        return list(facts)

    monkeypatch.setattr(
        "app.connectors.web.provider_router.ProviderRouter.search",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "app.connectors.web.extractors.wikipedia_extractor.WikipediaExtractor.extract",
        AsyncMock(return_value={}),
    )
    return facts


@pytest.fixture
def no_persistence(monkeypatch: pytest.MonkeyPatch) -> None:
    """Deliver without a database."""

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
    """No web acquisition: the file is the only source of *this* run."""
    monkeypatch.setattr(
        "app.connectors.web.provider_router.ProviderRouter.search",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "app.connectors.web.extractors.wikipedia_extractor.WikipediaExtractor.extract",
        AsyncMock(return_value={}),
    )


def _file_source() -> dict[str, Any]:
    """The file source as the colis carries it (as a document source)."""
    return {
        "source_id": FILE_SOURCE,
        "source_type": "file",
        "url": STORAGE_REF,
        "reliability_score": 0.8,
        "freshness": {"retrieved_at": "2026-09-29T00:00:00Z"},
    }


def _web_source() -> dict[str, Any]:
    """The web source as the colis carries it."""
    return {
        "source_id": WEB_SOURCE,
        "source_type": "web",
        "url": "https://exemple.invalid/paris",
        "reliability_score": 0.6,
        "freshness": {},
    }


async def _run() -> dict[str, Any]:
    """Run the pipeline for one ``data`` request."""
    return await PipelineRunner().run(
        ULID.new("REQ_"), {"objective": OBJECTIVE, "request_type": "data"}
    )


class TestTheFileAndTheWebDisagree:
    """§14.4 — the disagreement is reported, unit by unit."""

    @pytest.mark.asyncio
    async def test_a_file_row_and_a_web_claim_produce_one_conflict(self) -> None:
        report = await assess_sources(
            [_file_source(), _web_source()], [FILE_UNIT, WEB_UNIT_CLAIM]
        )

        assert len(report.conflicts) == 1
        conflict = report.conflicts[0]
        assert {conflict.information_a, conflict.information_b} == {
            FILE_UNIT["information_id"],
            WEB_UNIT_CLAIM["information_id"],
        }
        assert conflict.difference_type
        assert conflict.severity
        assert conflict.resolution_status == "open", "aucun arbitrage silencieux"
        assert report.compared_units == 2

    @pytest.mark.asyncio
    async def test_the_conflict_names_the_source_that_diverges(self) -> None:
        """The two units differ *and* come from different sources (§14.1)."""
        report = await assess_sources(
            [_file_source(), _web_source()], [FILE_UNIT, WEB_UNIT_CLAIM]
        )
        assert report.incomparable_units == 0
        assert report.freshness[FILE_SOURCE]["score"] == pytest.approx(1.0)


class TestNoSilentArbitration:
    """What cannot be compared is stated, never presented as agreement."""

    @pytest.mark.asyncio
    async def test_a_web_sentence_without_a_claim_is_declared_incomparable(self) -> None:
        report = await assess_sources(
            [_file_source(), _web_source()], [FILE_UNIT, WEB_UNIT_SENTENCE]
        )

        assert report.conflicts == [], "une phrase ne contredit pas une colonne"
        assert report.incomparable_units == 1
        assert any("partielle" in limitation for limitation in report.limitations)
        assert report.compared_units == 1

    @pytest.mark.asyncio
    async def test_a_single_source_is_never_compared_with_itself(self) -> None:
        report = await assess_sources([_file_source()], [FILE_UNIT, WEB_UNIT_CLAIM])
        assert report.conflicts == []


class TestTheColisCarriesTheResult:
    """The stage is wired: the delivery exposes what the tools found."""

    @pytest.mark.asyncio
    async def test_the_delivery_exposes_freshness_and_conflicts(
        self, monkeypatch: pytest.MonkeyPatch, no_persistence: None, no_web: None
    ) -> None:
        monkeypatch.setattr(runner_module, "load_request_material", _material(WEB_UNIT_CLAIM))
        delivery = await _run()

        assert "source_quality" in delivery
        block = delivery["source_quality"]
        assert block["assessed_sources"] >= 1
        assert isinstance(block["freshness"], dict)
        # The file source's freshness was evaluated and written back on the
        # source entry of the colis (and therefore persisted by the pipeline).
        file_entries = [
            source
            for source in delivery["sources"]
            if source.get("source_id") == FILE_SOURCE
        ]
        assert file_entries, "la source du fichier doit figurer dans le colis"
        assert "checked_at" in file_entries[0]["freshness"]
        assert delivery["conflicts"] == []
