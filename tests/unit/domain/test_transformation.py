"""§12.1 — a transformation is the traceable link between inputs and outputs.

§12 requires the RAW → NORMALIZED → ENRICHED → DERIVED lifecycle to be
replayable: every derived value must point at the operation and the inputs that
produced it. These tests pin the §12.1 record itself, including the two
invariants that make it auditable: a success produces output, and a failure
states why (§25.1).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.core.errors import ValidationError
from app.domain.entities.transformation import TRANSFORMATION_RESULTS, Transformation
from app.domain.value_objects.ulid import ULID
from tests.factories import make_transformation


def _trf_id() -> str:
    """Return a fresh ``TRF_{ULID}`` identifier."""
    return ULID.new("TRF_")


class TestTransformationRecord:
    """§12.1 — the JSON contract of one recorded operation."""

    def test_projection_carries_every_section_12_1_field(self) -> None:
        """``to_dict`` exposes exactly the §12.1 keys."""
        transformation = make_transformation()
        projected = transformation.to_dict()

        assert set(projected) == {
            "transformation_id",
            "input_ids",
            "output_ids",
            "operator",
            "tool",
            "tool_version",
            "parameters",
            "timestamp",
            "result",
            "justification",
        }

    def test_timestamp_is_serialised_as_utc_z(self) -> None:
        """The §12.1 timestamp is ISO 8601 UTC, like every other INIS instant."""
        moment = datetime(2026, 9, 28, 10, 30, tzinfo=UTC)
        projected = make_transformation(timestamp=moment).to_dict()

        assert projected["timestamp"] == "2026-09-28T10:30:00Z"

    def test_inputs_and_outputs_are_the_traceable_links(self) -> None:
        """The recorded ids are the ones the lineage graph is rebuilt from."""
        source_unit = ULID.new("INF_")
        derived_unit = ULID.new("INF_")
        transformation = make_transformation(
            input_ids=[source_unit], output_ids=[derived_unit]
        )

        assert transformation.input_ids == [source_unit]
        assert transformation.output_ids == [derived_unit]

    @pytest.mark.parametrize("result", TRANSFORMATION_RESULTS)
    def test_documented_results_are_accepted(self, result: str) -> None:
        """§12.1 defines exactly ``success`` and ``failure``."""
        transformation = make_transformation(
            result=result,
            output_ids=[ULID.new("INF_")] if result == "success" else [],
            justification="source unreachable",
        )
        transformation.validate()

        assert transformation.result == result


class TestTransformationInvariants:
    """§0.3 + §12.1 + §25.1 — the rules the record cannot be built around."""

    @pytest.mark.parametrize("bad_id", ["TRF_", "INF_01ARZ3NDEKTSV4RRFFQ69G5F77", "TRF_NOT_A_ULID"])
    def test_transformation_id_must_be_a_trf_ulid(self, bad_id: str) -> None:
        """§0.3 — a transformation id is always ``TRF_{ULID}``."""
        with pytest.raises(PydanticValidationError):
            Transformation(
                transformation_id=bad_id,
                input_ids=["SRC_x"],
                output_ids=[ULID.new("INF_")],
            )

    def test_success_without_output_is_refused(self) -> None:
        """A successful transformation that produced nothing is a contradiction."""
        transformation = make_transformation(result="success", output_ids=[])

        with pytest.raises(ValidationError, match="at least one output_id"):
            transformation.validate()

    def test_failure_without_justification_is_refused(self) -> None:
        """§25.1 — a failure must carry an explicit reason."""
        transformation = make_transformation(
            result="failure", output_ids=[], justification="   "
        )

        with pytest.raises(ValidationError, match="justification"):
            transformation.validate()

    def test_failure_with_justification_is_auditable(self) -> None:
        """A justified failure is a valid, replayable lineage node."""
        transformation = make_transformation(
            result="failure",
            output_ids=[],
            justification="The source returned HTTP 503 after 3 retries.",
        )
        transformation.validate()

        assert transformation.result == "failure"

    def test_fresh_identifier_is_unique_per_record(self) -> None:
        """Two transformations never share an identifier (§0.3)."""
        assert _trf_id() != _trf_id()

