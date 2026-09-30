"""§12 — every unit carries the stage it really reached, and no unit skips one.

The lifecycle of §12 is ``raw → normalized → enriched → derived``. Before L3.1
every produced unit was stamped ``raw`` whatever had happened to it, and nothing
refused a jump: a unit could be built by an extraction, enriched, persisted as
derived and the chain could not tell. These tests pin the two halves of the fix:

* the producers stamp the stage they actually reach — a fetched page is ``raw``,
  the located §11 unit an extraction builds out of it is ``normalized``;
* the only way to the next stage is :func:`advance_stage`, which refuses a jump
  (``raw`` → ``enriched``, ``normalized`` → ``derived``), a rewind and an
  unknown stage — the gap stays visible instead of being silently filled.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.core.constants import DATA_STAGES
from app.domain.entities.information_unit import InformationUnit
from app.knowledge.enrichment import (
    STAGE_ORDER,
    StageTransitionError,
    advance_stage,
    can_transition,
    enrich_units,
)
from app.knowledge.extraction.fact_extractor import FactExtractor
from app.knowledge.ingestion.document_ingestor import ingest_document

DOCUMENT_ID = "DOC_01M3Q0000000000000000000AA"
SOURCE_ID = "SRC_01M3Q0000000000000000000AA"
REQUEST_ID = "REQ_01M3Q0000000000000000000AA"
STORAGE_REF = "s3://inis-artifacts/documents/REQ_1/abc.csv"
CSV_BYTES = b"city,population\nParis,2145906\nBerlin,3645000\n"
URL = "https://example.test/report"
TEXT = "Le fournisseur a livré le 15/01/2024 et 12 kilos de café."


class TestTheStagesAreTheFourOfTheSpec:
    """§12 — one declaration, shared by the domain, the enricher and the lineage."""

    def test_the_constant_of_the_spec_is_the_one_used(self) -> None:
        assert STAGE_ORDER == DATA_STAGES
        assert STAGE_ORDER == ("raw", "normalized", "enriched", "derived")

    def test_the_domain_refuses_a_stage_outside_the_chain(self) -> None:
        payload = {
            "information_id": "INF_01M3Q0000000000000000000AA",
            "type": "text",
            "content": {"text": "Paris"},
            "raw_reference": {"url": URL},
            "source_id": SOURCE_ID,
            "document_id": DOCUMENT_ID,
            "dataset_id": None,
            "location": {},
            "context": {},
            "language": None,
            "unit": None,
            "time": {},
            "classification": {},
            "quality": {},
            "confidence": {"not_a_probability": True},
            "provenance": {"source_id": SOURCE_ID, "method": "test"},
            "versions": ["INF_01M3Q0000000000000000000AA"],
            "data_stage": "normalized",
        }

        # The four stages are the only accepted values, and the entity says so.
        assert InformationUnit(**payload).data_stage == "normalized"
        with pytest.raises(PydanticValidationError):
            InformationUnit(**{**payload, "data_stage": "enrichi"})


class TestTheProducersStampTheStageTheyReach:
    """§12 — a unit is born ``normalized``, never ``raw``: it is already a unit."""

    async def test_the_extraction_produces_normalized_units(self) -> None:
        facts = await FactExtractor().extract(TEXT, SOURCE_ID, DOCUMENT_ID, URL)

        assert facts
        assert {fact["data_stage"] for fact in facts} == {"normalized"}

    async def test_the_ingestion_produces_normalized_units(self) -> None:
        outcome = await ingest_document(
            document_id=DOCUMENT_ID,
            source_id=SOURCE_ID,
            request_id=REQUEST_ID,
            file_name="villes.csv",
            mime_type="text/csv",
            data=CSV_BYTES,
            storage_ref=STORAGE_REF,
        )

        assert outcome.units
        assert {unit["data_stage"] for unit in outcome.units} == {"normalized"}

    async def test_a_normalized_unit_is_then_enriched_by_the_next_step(self) -> None:
        facts = await FactExtractor().extract(TEXT, SOURCE_ID, DOCUMENT_ID, URL)
        outcome = enrich_units(facts)

        assert outcome.enriched_ids == [fact["information_id"] for fact in facts]
        assert {unit["data_stage"] for unit in outcome.units} == {"enriched"}


class TestNoStageIsEverSkipped:
    """§12/§0.2 — a jump is refused, a rewind is refused, an unknown stage too."""

    @pytest.mark.parametrize(
        ("origin", "target"),
        [
            ("raw", "enriched"),
            ("raw", "derived"),
            ("normalized", "derived"),
        ],
    )
    def test_a_downstream_stage_is_not_reachable(self, origin: str, target: str) -> None:
        with pytest.raises(StageTransitionError):
            advance_stage(origin, target)

    @pytest.mark.parametrize("origin", ["derived", "enriched", "normalized"])
    def test_a_stage_never_goes_backwards(self, origin: str) -> None:
        assert can_transition(origin, "raw") is False

    def test_an_unknown_stage_is_refused_on_both_sides(self) -> None:
        assert can_transition("raw", "enrichi") is False
        assert can_transition("inconnu", "normalized") is False

    def test_the_chain_is_walked_one_step_at_a_time(self) -> None:
        stage = "raw"
        for expected in ("normalized", "enriched", "derived"):
            stage = advance_stage(stage, expected)
            assert stage == expected

    def test_the_enricher_refuses_a_raw_to_enriched_jump(self) -> None:
        """The step of §12 does not relabel what it did not receive ready."""
        outcome = enrich_units(
            [
                {
                    "information_id": "INF_01M3Q0000000000000000000AA",
                    "content": {"text": TEXT},
                    "source_id": SOURCE_ID,
                    "data_stage": "raw",
                }
            ]
        )

        assert outcome.units == ()
        assert outcome.lineage() is None
