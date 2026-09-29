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
