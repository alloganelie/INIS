"""§12.1 — a run records one transformation per stage it really executed.

The audit found a single ``TRF_`` row per run, with the generic operator
``PipelineRunner`` and a parameter set that said nothing about what had happened
(C11): the lineage could not tell acquisition from extraction, from synthesis,
from the delivery of a file. These tests pin the replacement, and the rule that
matters most: a stage that produced nothing is **absent**, never recorded with a
fabricated result.
"""

from __future__ import annotations

import pytest

from app.domain.entities.transformation import Transformation
from app.domain.value_objects.ulid import ULID
from app.knowledge.provenance.stage_transformations import DATA_STAGES, build_transformations

REQUEST_ID = "REQ_01M3Q0000000000000000000AA"
OBJECTIVE = "Compare la population des villes."

SOURCES = [{"source_id": "SRC_01M3Q0000000000000000000AA"}]
UNITS = [
    {"information_id": "INF_01M3Q0000000000000000000AA"},
    {"information_id": "INF_01M3Q0000000000000000000AB"},
]
EVIDENCE = [{"evidence_id": "EVID_01M3Q0000000000000000000AA"}]
ARTIFACTS = [{"artifact_id": "ART_2026_000001"}]

#: §9.1 — material already ingested for the request (a CSV and its two rows).
INGESTED_DOCUMENTS = [
    {
        "document_id": "DOC_01M3Q0000000000000000000AA",
        "file_name": "villes.csv",
        "mime_type": "text/csv",
    }
]
INGESTED_UNITS = [
    {"information_id": "INF_01M3Q0000000000000000000BB"},
    {"information_id": "INF_01M3Q0000000000000000000BC"},
]
INGESTED = {
    "documents": INGESTED_DOCUMENTS,
    "units": INGESTED_UNITS,
    "readers": ["read_csv"],
}

#: §12 — le rapport de l'étape « normalized » → « enriched » du colis : les
#: unités réellement promues, la locale utilisée et les compteurs de l'enricher.
ENRICHMENT = {
    "tool": "Enricher.enrich",
    "unit_ids": ["INF_01M3Q0000000000000000000AA"],
    "values": 3,
    "languages": {"fr": 1},
    "locale": "fr-FR",
    "duplicates": 0,
    "unresolved": 1,
}


def _stages(transformations: list[dict]) -> list[str]:
    """Return the stage of each transformation, in order."""
    return [item["parameters"]["stage"] for item in transformations]


def _build(**overrides: object) -> list[dict]:
    """Build transformations for a full run, with per-test overrides."""
    arguments: dict = {
        "request_id": REQUEST_ID,
        "objective": OBJECTIVE,
        "sources": SOURCES,
        "information_units": UNITS,
        "evidence": EVIDENCE,
        "artifacts": ARTIFACTS,
    }
    arguments.update(overrides)
    return build_transformations(**arguments)


class TestStageRecording:
    """One row per stage, with the ids that stage really produced."""

    def test_a_full_run_records_the_four_stages_in_order(self) -> None:
        assert _stages(_build(model="openai/gpt-4")) == list(DATA_STAGES)

    def test_each_stage_names_its_tool_and_its_ids(self) -> None:
        by_stage = {item["parameters"]["stage"]: item for item in _build()}

        assert by_stage["raw"]["operator"] == "ProviderRouter"
        assert by_stage["raw"]["input_ids"] == [REQUEST_ID]
        assert by_stage["raw"]["output_ids"] == ["SRC_01M3Q0000000000000000000AA"]

        assert by_stage["normalized"]["input_ids"] == ["SRC_01M3Q0000000000000000000AA"]
        assert by_stage["normalized"]["output_ids"] == [
            "INF_01M3Q0000000000000000000AA",
            "INF_01M3Q0000000000000000000AB",
        ]

        assert by_stage["enriched"]["output_ids"] == ["EVID_01M3Q0000000000000000000AA"]
        assert by_stage["enriched"]["tool"] == "synthesis"

        assert by_stage["derived"]["tool"] == "ArtifactPackager.package"
        assert by_stage["derived"]["output_ids"] == ["ART_2026_000001"]

    def test_the_model_that_synthesised_is_recorded(self) -> None:
        enriched = next(
            item
            for item in _build(model="openai/gpt-4")
            if item["parameters"]["stage"] == "enriched"
        )

        assert enriched["tool"] == "openai/gpt-4"

    def test_every_row_is_a_valid_spec121_transformation(self) -> None:
        for item in _build():
            assert item["transformation_id"].startswith("TRF_")
            assert ULID.is_valid(item["transformation_id"])
            assert item["result"] == "success"
            assert item["output_ids"], "a successful transformation declares its output"
            assert REQUEST_ID in item["justification"]
            assert item["tool_version"]
            Transformation(**item).validate()

    def test_each_row_has_its_own_identifier(self) -> None:
        transformations = _build()

        identifiers = {item["transformation_id"] for item in transformations}
        assert len(identifiers) == len(transformations)


class TestAbsentStages:
    """§0.2 — a stage that produced nothing is not recorded."""

    def test_an_acquisition_only_run_records_one_stage(self) -> None:
        transformations = build_transformations(
            request_id=REQUEST_ID, objective=OBJECTIVE, sources=SOURCES
        )

        assert _stages(transformations) == ["raw"]

    def test_a_run_with_no_material_records_nothing(self) -> None:
        """No source, no unit, no evidence, no artifact: no transformation at all."""
        assert build_transformations(request_id=REQUEST_ID, objective=OBJECTIVE) == []

    def test_units_without_sources_still_record_the_normalized_stage(self) -> None:
        normalized = next(
            item
            for item in build_transformations(
                request_id=REQUEST_ID, objective=OBJECTIVE, information_units=UNITS
            )
            if item["parameters"]["stage"] == "normalized"
        )

        assert normalized["input_ids"] == [REQUEST_ID]

    def test_the_objective_is_kept_for_replay(self) -> None:
        transformations = build_transformations(
            request_id=REQUEST_ID, objective=OBJECTIVE, sources=SOURCES
        )

        assert transformations[0]["parameters"]["objective"] == OBJECTIVE


class TestIngestedFileStages:
    """§9.1 — un fichier a ses propres étages, produits par son propre lecteur."""

    def test_the_ingestion_is_recorded_as_its_own_stage_pair(self) -> None:
        """Un fichier seul : deux étages, et rien d'autre."""
        transformations = build_transformations(
            request_id=REQUEST_ID,
            objective=OBJECTIVE,
            ingested=INGESTED,
        )

        assert _stages(transformations) == ["raw", "normalized"]
        assert all(
            item["parameters"].get("origin") == "uploaded_document"
            for item in transformations
        )

    def test_the_reader_that_ran_is_the_tool_of_the_raw_stage(self) -> None:
        raw = next(
            item
            for item in _build(ingested=INGESTED)
            if item["parameters"].get("origin") == "uploaded_document"
            and item["parameters"]["stage"] == "raw"
        )

        assert raw["tool"] == "read_csv"
        assert raw["operator"] == "DocumentIngestor"
        assert raw["output_ids"] == ["DOC_01M3Q0000000000000000000AA"]
        assert raw["input_ids"] == [REQUEST_ID]
        assert raw["parameters"]["documents"] == 1

    def test_the_file_units_are_not_claimed_by_the_fact_extractor(self) -> None:
        """§0.2 — l'extraction web ne s'attribue jamais les unités d'un fichier."""
        transformations = _build(
            sources=(), information_units=(), ingested=INGESTED
        )

        extraction_tools = {item["tool"] for item in transformations}
        assert "FactExtractor.extract" not in extraction_tools
        normalized = next(
            item for item in transformations if item["parameters"]["stage"] == "normalized"
        )
        assert normalized["output_ids"] == [
            "INF_01M3Q0000000000000000000BB",
            "INF_01M3Q0000000000000000000BC",
        ]
        assert normalized["input_ids"] == ["DOC_01M3Q0000000000000000000AA"]

    def test_web_and_file_producers_coexist_without_merging(self) -> None:
        """Deux producteurs, deux lignes : le lignage nomme qui a produit quoi."""
        transformations = _build(ingested=INGESTED)

        producers: dict[str, list[str]] = {}
        for item in transformations:
            producers.setdefault(item["parameters"]["stage"], []).append(item["tool"])

        assert producers["raw"] == ["ProviderRouter.search", "read_csv"]
        assert producers["normalized"] == [
            "FactExtractor.extract",
            "DocumentIngestor.ingest",
        ]

    def test_the_stage_order_of_spec12_is_kept(self) -> None:
        transformations = _build(ingested=INGESTED)

        assert _stages(transformations) == [
            "raw",
            "raw",
            "normalized",
            "normalized",
            "enriched",
            "derived",
        ]

    def test_the_derived_stage_inputs_both_producers(self) -> None:
        derived = next(
            item
            for item in _build(ingested=INGESTED)
            if item["parameters"]["stage"] == "derived"
        )

        assert derived["input_ids"] == [
            "INF_01M3Q0000000000000000000AA",
            "INF_01M3Q0000000000000000000AB",
            "INF_01M3Q0000000000000000000BB",
            "INF_01M3Q0000000000000000000BC",
        ]

    def test_an_empty_ingestion_records_nothing(self) -> None:
        """§0.2 — pas de fichier lu, pas d'étage fichier."""
        transformations = _build(
            ingested={"documents": [], "units": [], "readers": []}
        )

        assert _stages(transformations) == list(DATA_STAGES)

    def test_every_ingestion_row_is_a_valid_spec121_transformation(self) -> None:
        for item in _build(ingested=INGESTED):
            Transformation(**item).validate()
            assert item["output_ids"]
            assert item["result"] == "success"


class TestDegradedRuns:
    """A stage that failed is not silently reported as successful."""

    def test_a_finding_without_evidence_records_no_enriched_stage(self) -> None:
        """§0.2 — the synthesis produced no traceable output, so it is not claimed."""
        transformations = build_transformations(
            request_id=REQUEST_ID,
            objective=OBJECTIVE,
            information_units=UNITS,
            findings=[{"finding": "Fait sans preuve", "source_id": "SRC_X"}],
        )

        assert "enriched" not in _stages(transformations)
        assert "derived" not in _stages(transformations)

    def test_the_entity_refuses_a_non_trf_identifier(self) -> None:
        """Guard: the module is importable and the entity really validates (P3)."""
        with pytest.raises(ValueError):
            Transformation(transformation_id="ART_2026_000001", output_ids=["INF_1"])


class TestEnrichmentIsItsOwnStage:
    """§12.1 — l'étape « enriched » de l'enricher a sa propre ligne.

    La synthèse et l'enrichissement atteignent le **même** stade §12 par deux
    opérations différentes : créditer l'une du travail de l'autre rendrait le
    lignage faux, exactement ce que L3.1 corrige.
    """

    def test_the_two_producers_of_the_stage_are_kept_apart(self) -> None:
        producers = [
            item["tool"]
            for item in _build(enrichment=ENRICHMENT)
            if item["parameters"]["stage"] == "enriched"
        ]

        assert producers == ["Enricher.enrich", "synthesis"]

    def test_the_enriched_units_are_the_output_of_the_enricher(self) -> None:
        row = next(
            item
            for item in _build(enrichment=ENRICHMENT)
            if item["tool"] == "Enricher.enrich"
        )

        assert row["operator"] == "Enricher"
        assert row["output_ids"] == ["INF_01M3Q0000000000000000000AA"]
        assert row["input_ids"] == [
            "INF_01M3Q0000000000000000000AA",
            "INF_01M3Q0000000000000000000AB",
        ]

    def test_the_counters_of_the_enricher_are_replayed(self) -> None:
        row = next(
            item
            for item in _build(enrichment=ENRICHMENT)
            if item["tool"] == "Enricher.enrich"
        )

        assert row["parameters"]["values"] == 3
        assert row["parameters"]["languages"] == {"fr": 1}
        assert row["parameters"]["locale"] == "fr-FR"
        assert row["parameters"]["unresolved"] == 1

    def test_a_run_that_enriched_nothing_records_no_such_row(self) -> None:
        assert all(item["tool"] != "Enricher.enrich" for item in _build())

    def test_an_enrichment_without_output_records_nothing(self) -> None:
        """§0.2 — pas d'unité promue, pas d'étape revendiquée."""
        assert _stages(_build(enrichment={"unit_ids": []})) == list(DATA_STAGES)

    def test_every_enrichment_row_is_a_valid_spec121_transformation(self) -> None:
        for item in _build(enrichment=ENRICHMENT):
            Transformation(**item).validate()
            assert item["output_ids"]
