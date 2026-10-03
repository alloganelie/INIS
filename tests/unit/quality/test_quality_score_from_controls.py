"""§13.3 — the quality score of a delivered dataset comes from real checks.

The plan's criterion for L5 is blunt: a CSV with duplicates, missing values and
an inconsistency must produce a colis where those three defects are *explicitly
listed*, and ``datasets[].quality_score`` must not be ``None`` when the controls
ran. ``None`` stays reserved for "not measured".

These tests exercise the module the pipeline calls
(:mod:`app.quality.dataset_quality`) on the same shapes a real ingestion
produces: the rows are the §11 units of the dataset, and the checks are the §13.2
tools of ``app/tools/files/dataset_inspector.py``.
"""

from __future__ import annotations

import pytest

from app.quality.dataset_quality import CHECK_NAMES, assess_datasets

DATASET_ID = "DATA_L5_1"

#: A tabular payload with the three defects of the plan's exit criterion.
DIRTY_ROWS = [
    {"ville": "Paris", "population": 2148000, "annee": 2024},
    {"ville": "Lyon", "population": 522250, "annee": 2024},
    # duplicate of the previous record
    {"ville": "Lyon", "population": 522250, "annee": 2024},
    # missing value
    {"ville": "Marseille", "population": None, "annee": 2024},
    # the same column is a number everywhere else (inconsistent column)
    {"ville": "Nice", "population": "342 522", "annee": 2023},
    {"ville": "Nimes", "population": 148561, "annee": 2025},
]

CLEAN_ROWS = [
    {"ville": "Paris", "population": 2148000, "annee": 2024},
    {"ville": "Lyon", "population": 522250, "annee": 2024},
    {"ville": "Nimes", "population": 148561, "annee": 2025},
]


def _dataset() -> dict:
    """Return the ``datasets[]`` entry of the colis."""
    return {"dataset_id": DATASET_ID, "row_count": len(DIRTY_ROWS), "dataset_schema": {}}


def _units(rows: list[dict]) -> list[dict]:
    """Return the §11 units that carry those rows."""
    return [
        {
            "information_id": f"INF_L5_{index}",
            "dataset_id": DATASET_ID,
            "type": "table_row",
            "content": row,
        }
        for index, row in enumerate(rows)
    ]


class TestTheThreeDefects:
    """The exit criterion of L5, item by item."""

    @pytest.mark.asyncio
    async def test_score_is_not_none_when_the_controls_ran(self) -> None:
        report = await assess_datasets([_dataset()], _units(DIRTY_ROWS))
        block = report.datasets[DATASET_ID]
        assert block["quality_score"] is not None
        assert 0.0 <= block["quality_score"] <= 1.0
        assert block["rows_examined"] == len(DIRTY_ROWS)
        assert set(block["checks"]) == set(CHECK_NAMES)

    @pytest.mark.asyncio
    async def test_missing_value_is_named(self) -> None:
        report = await assess_datasets([_dataset()], _units(DIRTY_ROWS))
        assert any("population" in issue for issue in report.datasets[DATASET_ID]["issues"])
        assert report.datasets[DATASET_ID]["checks"]["completeness"] < 1.0

    @pytest.mark.asyncio
    async def test_duplicate_is_named_with_its_rows(self) -> None:
        report = await assess_datasets([_dataset()], _units(DIRTY_ROWS))
        duplicates = [
            issue for issue in report.datasets[DATASET_ID]["issues"] if "doublon" in issue
        ]
        assert duplicates, "le doublon doit être listé"
        assert "lignes 1, 2" in duplicates[0]
        assert report.datasets[DATASET_ID]["checks"]["uniqueness"] < 1.0

    @pytest.mark.asyncio
    async def test_inconsistent_column_is_named(self) -> None:
        report = await assess_datasets([_dataset()], _units(DIRTY_ROWS))
        issues = report.datasets[DATASET_ID]["issues"]
        assert any("mixes types" in issue for issue in issues), issues
        assert report.datasets[DATASET_ID]["checks"]["consistency"] < 1.0

    @pytest.mark.asyncio
    async def test_every_issue_becomes_a_limitation_of_the_colis(self) -> None:
        report = await assess_datasets([_dataset()], _units(DIRTY_ROWS))
        joined = " | ".join(report.limitations)
        assert "population" in joined  # missing value
        assert "doublon" in joined  # duplicate
        assert "mixes types" in joined  # inconsistency
        assert all(DATASET_ID in limitation for limitation in report.limitations)


class TestHonesty:
    """What the report says when it cannot measure anything (§13.3, §37)."""

    @pytest.mark.asyncio
    async def test_without_rows_the_score_is_none_and_stated(self) -> None:
        report = await assess_datasets([_dataset()], [])
        block = report.datasets[DATASET_ID]
        assert block["quality_score"] is None
        assert block["rows_examined"] == 0
        assert any("non mesurée" in limitation for limitation in report.limitations)
        assert any(DATASET_ID in item for item in report.missing_information)

    @pytest.mark.asyncio
    async def test_a_clean_dataset_scores_high_without_issues(self) -> None:
        report = await assess_datasets([_dataset()], _units(CLEAN_ROWS))
        block = report.datasets[DATASET_ID]
        assert block["issues"] == []
        assert block["quality_score"] == pytest.approx(1.0)
        assert report.limitations == []

    @pytest.mark.asyncio
    async def test_units_of_another_dataset_are_ignored(self) -> None:
        units = _units(CLEAN_ROWS)
        units.append({"information_id": "INF_OTHER", "dataset_id": "DATA_OTHER", "content": {}})
        report = await assess_datasets([_dataset()], units)
        assert report.datasets[DATASET_ID]["rows_examined"] == len(CLEAN_ROWS)

    @pytest.mark.asyncio
    async def test_no_dataset_is_not_a_failure(self) -> None:
        report = await assess_datasets([], _units(CLEAN_ROWS))
        assert report.datasets == {}
        assert report.limitations == []
        assert report.to_dict()["checks"] == list(CHECK_NAMES)

    @pytest.mark.asyncio
    async def test_a_record_unit_is_unwrapped_to_its_values(self) -> None:
        """A real ingestion stores the row under ``content["values"]``.

        Without unwrapping, the controls would examine a single ``values``
        column and report a confident score about the wrong shape — the kind of
        silent nonsense this lot exists to prevent.
        """
        units = [
            {
                "information_id": f"INF_L5_R{index}",
                "dataset_id": DATASET_ID,
                "type": "record",
                "content": {"values": row, "text": " | ".join(str(v) for v in row.values())},
            }
            for index, row in enumerate(DIRTY_ROWS)
        ]
        report = await assess_datasets([_dataset()], units)
        issues = report.datasets[DATASET_ID]["issues"]
        assert any("population" in issue for issue in issues)
        assert not any("values" in issue for issue in issues)
