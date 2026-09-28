"""Tests for GDPRHandler rectification & portability per §41.9 (§Art. 16/20)."""

from datetime import datetime
from datetime import timezone

import pytest

from app.governance.retention.gdpr_handler import EXPORTABLE_TYPES
from app.governance.retention.gdpr_handler import GDPRHandler

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


class TestRectification:
    """Art. 16 — correct an erroneous unit without breaking traceability."""

    def _unit(self) -> dict:
        return {
            "information_id": "INF_01OLD",
            "content": {"subject": "temp", "value": 20.0},
            "actor_id": "actor-1",
            "data_stage": "raw",
        }

    def test_rectify_supersedes_and_derives_new_record(self) -> None:
        handler = GDPRHandler()
        unit = self._unit()

        result = handler.rectify_information_unit(
            unit,
            corrected_content={"subject": "temp", "value": 21.5},
            transformation_id="TRF_01",
            reason="measurement typo",
        )

        superseded, corrected = result["superseded"], result["corrected"]
        # Old record kept, only linked forward — provenance intact (§12).
        assert superseded["information_id"] == "INF_01OLD"
        assert superseded["superseded_by"] == corrected["information_id"]
        assert superseded["content"] == unit["content"]
        # New record is DERIVED, carries the transformation and back-link.
        assert corrected["data_stage"] == "derived"
        assert corrected["transformation_id"] == "TRF_01"
        assert corrected["supersedes"] == "INF_01OLD"
        assert corrected["content"] == {"subject": "temp", "value": 21.5}
        assert corrected["information_id"].startswith("INF_")
        assert result["information_id"] == "INF_01OLD"

    def test_rectify_keeps_inputs_untouched(self) -> None:
        handler = GDPRHandler()
        unit = self._unit()

        handler.rectify_information_unit(
            unit,
            corrected_content={},
            transformation_id="TRF_01",
            new_information_id="INF_01NEW",
        )

        assert "superseded_by" not in unit
        assert unit["data_stage"] == "raw"
        assert unit["content"] == {"subject": "temp", "value": 20.0}

    @pytest.mark.parametrize(
        ("unit", "transformation_id", "match"),
        [
            ("not-a-dict", "TRF_01", "unit must be a dict"),
            ({"content": "x"}, "TRF_01", "information_id"),
            ({"information_id": "INF_1"}, "", "transformation_id"),
        ],
    )
    def test_rectify_rejects_invalid_input(self, unit, transformation_id, match) -> None:
        with pytest.raises(ValueError, match=match):
            GDPRHandler().rectify_information_unit(
                unit,
                corrected_content={},
                transformation_id=transformation_id,
            )

    def test_rectify_rejects_reused_information_id(self) -> None:
        with pytest.raises(ValueError, match="new information_id"):
            GDPRHandler().rectify_information_unit(
                self._unit(),
                corrected_content={},
                transformation_id="TRF_01",
                new_information_id="INF_01OLD",
            )


class TestPortability:
    """Art. 20 — export every record linked to a requesting agent."""

    def test_export_groups_only_owned_records(self) -> None:
        handler = GDPRHandler()
        events = [
            {"audit_id": "a1", "actor_id": "actor-1"},
            {"audit_id": "a2", "actor_id": "actor-2"},
        ]
        units = [
            {"information_id": "i1", "agent_id": "actor-1"},
            {"information_id": "i2", "actor_id": "actor-2"},
        ]

        export = handler.export_actor_data(
            "actor-1",
            now=NOW,
            audit_events=events,
            information_units=units,
        )

        assert export["actor_id"] == "actor-1"
        assert export["exported_at"] == NOW.isoformat()
        assert export["counts"] == {"audit_events": 1, "information_units": 1}
        assert export["data"]["audit_events"][0]["audit_id"] == "a1"
        assert export["data"]["information_units"][0]["information_id"] == "i1"
        # Inputs are never mutated or aliased.
        assert events[0]["actor_id"] == "actor-1"
        export["data"]["audit_events"][0]["actor_id"] = "mutated"
        assert events[0]["actor_id"] == "actor-1"

    def test_exportable_types_match_the_retention_keys(self) -> None:
        assert EXPORTABLE_TYPES == (
            "audit_events",
            "information_units",
            "pii_data",
            "embeddings",
            "artifacts",
        )

    def test_export_rejects_unknown_resource_type(self) -> None:
        with pytest.raises(ValueError, match="Unknown resource types"):
            GDPRHandler().export_actor_data("actor-1", logs=[])

    def test_export_rejects_empty_actor_id(self) -> None:
        with pytest.raises(ValueError, match="actor_id"):
            GDPRHandler().export_actor_data("", audit_events=[])

