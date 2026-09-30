"""§13.2/§13.3 — quality of the datasets a delivery carries.

The checks already existed (``app/tools/files/dataset_inspector.py``,
``app/quality/checks/*``) but nothing ran them on the datasets the pipeline
delivers: ``datasets[].quality_score`` stayed ``None`` and the defects of an
ingested CSV (duplicates, missing values, inconsistencies) never reached the
colis, so a reader could not tell a clean file from a doubtful one.

This module is the missing link, and it holds three rules:

* the rows are the §11 units already stored for that dataset — nothing is
  re-read from a file the pipeline does not hold, and nothing is invented;
* a dataset whose rows are not in the colis gets ``quality_score = None`` **and**
  a stated limitation: ``None`` means "not measured", never "good";
* every issue a check reports is copied verbatim into the report, then into the
  delivery's ``limitations``/``missing_information`` (§24.1): §37 « signaler >
  inventer » applies to quality as it does to the rest.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from app.domain.entities.quality_result import QualityResult
from app.quality.score.quality_reporter import report
from app.tools.files.dataset_inspector import (
    check_consistency,
    check_missing_values,
    detect_duplicates,
    inspect_schema,
    profile_dataset,
    validate_schema,
)

__all__ = ["DatasetQualityReport", "assess_datasets"]

#: §13.3 metric names, in the order they are reported.
CHECK_NAMES = ("completeness", "uniqueness", "consistency", "validity")


class DatasetQualityReport:
    """The §13.2 checks and the §13.3 score of the delivered datasets."""

    def __init__(self) -> None:
        self.datasets: dict[str, dict[str, Any]] = {}
        self.limitations: list[str] = []
        self.missing_information: list[str] = []

    def to_dict(self) -> dict[str, Any]:
        """Return the delivery-level ``quality`` block."""
        return {
            "datasets": self.datasets,
            "checks": list(CHECK_NAMES),
            "not_a_probability": True,
        }


def _rows_by_dataset(
    units: Sequence[Mapping[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Group the delivered units' rows by the dataset they belong to.

    A record unit stores its row under ``content["values"]`` (that is what
    ``DocumentIngestor`` writes for a tabular payload, next to a ``text``
    rendering). Unwrapping it here is what makes the §13.2 checks examine the
    real columns: run on the raw content, they would see a single ``values``
    column and report a meaningless — yet confident — score.
    """
    grouped: dict[str, list[dict[str, Any]]] = {}
    for unit in units:
        dataset_id = unit.get("dataset_id")
        if not dataset_id:
            continue
        content = unit.get("content")
        if not isinstance(content, Mapping):
            continue
        values = content.get("values")
        row = dict(values) if isinstance(values, Mapping) else dict(content)
        grouped.setdefault(str(dataset_id), []).append(row)
    return grouped


def _duplicate_issue(duplicates: Sequence[Any], rows: int) -> tuple[float, str | None]:
    """Return the uniqueness score of *rows* and the issue it deserves.

    ``detect_duplicates`` reports the offending rows, not a score: the share of
    unique rows is computed here so it is comparable with the other §13.3
    metrics. The issue names the duplicated rows by index — a reader must be
    able to go and look, not merely be told "there are duplicates".
    """
    score = max(0.0, 1.0 - (len(duplicates) / float(rows))) if rows else 1.0
    if not duplicates:
        return score, None
    indexes: list[int] = []
    for duplicate in duplicates:
        positions = getattr(duplicate, "row_indexes", None)
        if isinstance(positions, (list, tuple)):
            indexes.extend(int(position) for position in positions)
    location = f" (lignes {', '.join(str(i) for i in sorted(set(indexes)))})" if indexes else ""
    return score, (
        f"{len(duplicates)} doublon(s) détecté(s) sur {rows} enregistrement(s){location}"
    )


async def _assess_one(
    dataset: Mapping[str, Any],
    rows: Sequence[dict[str, Any]],
    collected: DatasetQualityReport,
) -> None:
    """Run the §13.2 checks on one dataset and record their outcome."""
    dataset_id = str(dataset.get("dataset_id") or "")

    if not rows:
        # ``None`` is the honest answer: the controls did not run, and a score
        # would be a claim about data nobody looked at.
        collected.datasets[dataset_id] = {
            "quality_score": None,
            "checks": {},
            "issues": [],
            "rows_examined": 0,
        }
        collected.limitations.append(
            f"Qualité §13.2 non mesurée pour le dataset {dataset_id} : ses lignes ne sont pas "
            "dans le colis (les contrôles ne portent pas sur un schéma seul)."
        )
        collected.missing_information.append(
            f"qualité du dataset {dataset_id} (doublons, valeurs manquantes, incohérences)"
        )
        return

    results: dict[str, float] = {}
    issues: list[str] = []
    details: dict[str, Any] = {}

    completeness: QualityResult = await check_missing_values(rows)
    results["completeness"] = float(completeness.score)
    issues.extend(completeness.issues)
    details["completeness"] = completeness.details

    duplicates = await detect_duplicates(rows)
    uniqueness, duplicate_issue = _duplicate_issue(duplicates, len(rows))
    results["uniqueness"] = uniqueness
    details["uniqueness"] = {"duplicates": len(duplicates), "rows": len(rows)}
    if duplicate_issue:
        issues.append(duplicate_issue)

    consistency: QualityResult = await check_consistency(rows)
    results["consistency"] = float(consistency.score)
    issues.extend(consistency.issues)
    details["consistency"] = consistency.details

    # §13.2 — the inferred schema of the payload is what makes an incoherent
    # *cell* visible: a column that is a number everywhere else but carries
    # ``beaucoup`` in one row is a schema violation, not a detail. Without this
    # control the value was stored as text and the colis never said so.
    schema = await inspect_schema(rows)
    validation = await validate_schema(rows, schema)
    violations = list(getattr(validation, "violations", []) or [])
    results["validity"] = max(0.0, 1.0 - (len(violations) / float(len(rows))))
    details["validity"] = {
        "schema": schema.model_dump() if hasattr(schema, "model_dump") else {},
        "violations": [
            {
                "row_index": getattr(violation, "row_index", None),
                "field": getattr(violation, "field", None),
                "expected": getattr(violation, "expected", None),
                "observed": getattr(violation, "observed", None),
            }
            for violation in violations
        ],
    }
    for violation in violations:
        field = getattr(violation, "field", "?")
        expected = getattr(violation, "expected", "?")
        observed = getattr(violation, "observed", "?")
        row_index = getattr(violation, "row_index", "?")
        issues.append(
            f"ligne {row_index} : '{field}' attendu {expected}, observé {observed}"
        )

    profile = await profile_dataset(rows)
    score_report = await report(dict(dataset), results)

    collected.datasets[dataset_id] = {
        "quality_score": float(score_report["overall_score"]),
        "checks": {name: results.get(name) for name in CHECK_NAMES},
        "issues": issues,
        "details": details,
        "rows_examined": len(rows),
        "profile": profile.model_dump() if hasattr(profile, "model_dump") else {},
        "explanation": score_report.get("summary"),
        "not_a_probability": True,
    }
    for issue in issues:
        collected.limitations.append(f"Qualité §13.2 (dataset {dataset_id}) : {issue}")


async def assess_datasets(
    datasets: Sequence[Mapping[str, Any]],
    units: Sequence[Mapping[str, Any]],
) -> DatasetQualityReport:
    """Run the §13.2 checks on every delivered dataset and score it (§13.3).

    Args:
        datasets: The ``datasets[]`` of the colis (``dataset_id``, ``row_count``,
            ``dataset_schema``).
        units: The delivered §11 units; the ones carrying a ``dataset_id`` hold
            the rows the controls examine.

    Returns:
        A report whose ``datasets`` mapping is keyed by ``dataset_id``, plus the
        limitations and missing information the delivery must carry.
    """
    collected = DatasetQualityReport()
    grouped = _rows_by_dataset(units)
    for dataset in datasets:
        dataset_id = str(dataset.get("dataset_id") or "")
        await _assess_one(dataset, grouped.get(dataset_id, []), collected)
    return collected
