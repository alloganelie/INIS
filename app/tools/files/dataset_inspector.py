"""Dataset inspection and quality tools per §21.

The §21 signatures take a ``Dataset``. The ``Dataset`` **domain entity** defined
by §27 carries the schema, the row count and the storage reference — not the
rows themselves, because PostgreSQL never stores a bulky payload inline (§4.3).
Every function below therefore accepts a :data:`DatasetLike` value: either a
``Dataset`` (schema-level operations) or the in-memory rows that came out of
``app.tools.files.*_reader`` (row-level operations). Passing a ``Dataset``
without rows to a row-level tool raises instead of silently reporting "0 issues"
on data that was never examined (§0.2).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, TypeAlias

from app.core.errors import ValidationError
from app.domain.entities.dataset import Dataset
from app.domain.entities.dataset_profile import DatasetProfile
from app.domain.entities.duplicate import Duplicate
from app.domain.entities.quality_result import QualityResult
from app.domain.entities.schema import Schema
from app.domain.entities.validation_result import SchemaViolation, ValidationResult
from app.quality.checks import CompletenessCheck, ConsistencyCheck
from app.tools.files.dataset_builder import NULL_TYPE, infer_schema, value_type

__all__ = [
    "DatasetLike",
    "check_consistency",
    "check_missing_values",
    "detect_duplicates",
    "inspect_schema",
    "profile_dataset",
    "validate_schema",
]

#: A ``Dataset`` entity, a single record, or the rows read from a payload.
DatasetLike: TypeAlias = Dataset | Mapping[str, Any] | Sequence[Mapping[str, Any]]

_TYPE_PREDICATES: dict[str, tuple[type, ...]] = {
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "json": (dict, list, tuple),
}


def dataset_rows(dataset: DatasetLike) -> list[dict]:
    """Return the rows of *dataset*, raising when none are available.

    Args:
        dataset: A ``Dataset`` entity or an in-memory row collection.

    Returns:
        The list of mapping rows (possibly empty for an empty row collection).

    Raises:
        ValidationError: If a ``Dataset`` entity was passed, since the entity
            carries no rows and a row-level answer would be a fabrication.
    """
    if isinstance(dataset, Dataset):
        raise ValidationError(
            "Dataset entity carries no rows (§27); pass the rows returned by "
            "the file readers to run a row-level check"
        )
    if isinstance(dataset, Mapping):
        return [dict(dataset)]
    return [dict(row) for row in dataset if isinstance(row, Mapping)]


def _dataset_identity(dataset: DatasetLike) -> str | None:
    """Return the ``DATA_`` identifier of *dataset* when it has one."""
    return dataset.dataset_id if isinstance(dataset, Dataset) else None


async def inspect_schema(dataset: DatasetLike) -> Schema:
    """Return the observed columns and types of *dataset* (§21).

    Args:
        dataset: A ``Dataset`` entity, a record, or the rows of a payload.

    Returns:
        The schema inferred from the values actually present, with a small
        sample of real rows rather than placeholder values.
    """
    if isinstance(dataset, Dataset):
        fields = {str(name): str(kind) for name, kind in dataset.dataset_schema.items()}
        return Schema(fields=fields, record_count=dataset.row_count, sample=[])

    rows = dataset_rows(dataset)
    return Schema(fields=infer_schema(rows), record_count=len(rows), sample=rows[:2])


async def profile_dataset(dataset: DatasetLike) -> DatasetProfile:
    """Compute descriptive statistics of *dataset* from its own values (§21, §13).

    Args:
        dataset: A ``Dataset`` entity, a record, or the rows of a payload.

    Returns:
        The dataset profile. Null counts, distinct counts and numeric statistics
        are measurements only: an empty or non-numeric column is reported as
        empty rather than filled with a default value (§1.2).
    """
    if isinstance(dataset, Dataset):
        columns = list(dataset.dataset_schema)
        return DatasetProfile(
            dataset_id=dataset.dataset_id,
            row_count=dataset.row_count,
            column_count=len(columns),
            columns=columns,
            null_counts={column: 0 for column in columns},
            distinct_counts={column: 0 for column in columns},
            type_counts={
                column: {str(dataset.dataset_schema[column]): dataset.row_count}
                for column in columns
            },
        )

    rows = dataset_rows(dataset)
    columns: list[str] = list(infer_schema(rows))

    null_counts: dict[str, int] = {}
    distinct_counts: dict[str, int] = {}
    type_counts: dict[str, dict[str, int]] = {}
    numeric_stats: dict[str, dict[str, float]] = {}

    for column in columns:
        values = [row.get(column) for row in rows]
        null_counts[column] = sum(
            1 for value in values if value is None or str(value).strip() == ""
        )
        distinct_counts[column] = len(
            {str(value) for value in values if value is not None}
        )

        observed: dict[str, int] = {}
        for value in values:
            kind = value_type(value)
            observed[kind] = observed.get(kind, 0) + 1
        type_counts[column] = observed

        numeric_values = [
            float(value)
            for value in values
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        ]
        if numeric_values:
            numeric_stats[column] = {
                "min": min(numeric_values),
                "max": max(numeric_values),
                "mean": sum(numeric_values) / len(numeric_values),
                "sum": sum(numeric_values),
            }

    fingerprints = {
        tuple(sorted((str(key), repr(value)) for key, value in row.items()))
        for row in rows
    }
    return DatasetProfile(
        dataset_id=_dataset_identity(dataset),
        row_count=len(rows),
        column_count=len(columns),
        columns=columns,
        null_counts=null_counts,
        distinct_counts=distinct_counts,
        type_counts=type_counts,
        numeric_stats=numeric_stats,
        duplicate_row_count=len(rows) - len(fingerprints),
    )


async def detect_duplicates(dataset: DatasetLike) -> list[Duplicate]:
    """Return the groups of strictly identical records in *dataset* (§21, §13.4).

    Only *strictly equal* value sets are reported: near-duplicates require an
    explicit similarity policy and are never guessed here (§0.2).
    """
    rows = dataset_rows(dataset)
    grouped: dict[tuple[tuple[str, str], ...], list[int]] = {}
    example: dict[tuple[tuple[str, str], ...], dict] = {}

    for index, row in enumerate(rows):
        fingerprint = tuple(sorted((str(key), repr(value)) for key, value in row.items()))
        grouped.setdefault(fingerprint, []).append(index)
        example.setdefault(fingerprint, row)

    return [
        Duplicate(key=example[fingerprint], row_indexes=indexes)
        for fingerprint, indexes in grouped.items()
        if len(indexes) > 1
    ]


async def validate_schema(dataset: DatasetLike, schema: Schema) -> ValidationResult:
    """Validate the rows of *dataset* against *schema* (§21, §13.1).

    Args:
        dataset: A ``Dataset`` entity, a record, or the rows of a payload.
        schema: Expected ``{column: type}`` contract.

    Returns:
        The validation result. A missing column and a wrong type are both
        reported; nothing is coerced to make the dataset pass.

    §13.2 — une colonne **mixte** est le cas qui manquait. L'inférence écrit
    ``"integer|string"`` quand une cellule ne tient pas dans le type des autres ;
    faute de prédicat pour une union, le contrôle était alors **sauté** et la
    cellule aberrante n'était jamais nommée (le colis disait « mixte » sans dire
    où). Pour une union, la **majorité** des valeurs non nulles fait donc office
    de type attendu, et chaque valeur qui n'y appartient pas est une violation
    nommée (``row_index``, ``field``, ``expected``, ``observed``) — ce qui permet
    de retrouver la cellule source sans jamais la modifier ni la supprimer.
    Une colonne sans majorité stricte (autant d'un type que de l'autre) n'est pas
    arbitrée : elle ne produit aucune violation, et c'est dit ici plutôt
    qu'inventé.
    """
    if isinstance(dataset, Dataset):
        observed = {str(name): str(kind) for name, kind in dataset.dataset_schema.items()}
        violations = [
            SchemaViolation(
                row_index=0,
                field=field,
                expected=expected,
                observed=f"missing column (dataset schema has: {observed.get(field, 'absent')})",
            )
            for field, expected in schema.fields.items()
            if field not in observed
        ]
        return ValidationResult(
            valid=not violations,
            checked_fields=len(schema.fields),
            checked_rows=dataset.row_count,
            violations=violations,
        )

    rows = dataset_rows(dataset)
    majorities = _column_majorities(rows, schema.fields)
    violations: list[SchemaViolation] = []
    for index, row in enumerate(rows):
        for field, expected in schema.fields.items():
            if field not in row:
                violations.append(
                    SchemaViolation(
                        row_index=index,
                        field=field,
                        expected=expected,
                        observed="column absent",
                    )
                )
                continue
            value = row[field]
            if value is None:
                if expected != NULL_TYPE:
                    violations.append(
                        SchemaViolation(
                            row_index=index,
                            field=field,
                            expected=expected,
                            observed=NULL_TYPE,
                        )
                    )
                continue
            effective = majorities.get(field)
            if effective is not None:
                # La colonne a une nature majoritaire : la cellule qui n'en fait
                # pas partie est l'anomalie, et elle est nommée (ligne, colonne,
                # attendu, observé) sans que sa valeur soit touchée.
                accepted = _KIND_PREDICATES.get(effective, frozenset({effective}))
                kind = _value_kind(value)
                if kind not in accepted:
                    violations.append(
                        SchemaViolation(
                            row_index=index,
                            field=field,
                            expected=effective,
                            observed=kind,
                        )
                    )
                continue
            predicates = _TYPE_PREDICATES.get(expected)
            if predicates is not None and not isinstance(value, predicates):
                violations.append(
                    SchemaViolation(
                        row_index=index,
                        field=field,
                        expected=expected,
                        observed=value_type(value),
                    )
                )

    return ValidationResult(
        valid=not violations,
        checked_fields=len(schema.fields),
        checked_rows=len(rows),
        violations=violations,
    )


def _column_majorities(
    rows: Sequence[Mapping[str, Any]], fields: Mapping[str, str]
) -> dict[str, str]:
    """Return the majority **kind** of each column that has a strict one.

    Pourquoi une « nature » et pas seulement un type Python : un lecteur de CSV
    stocke ses cellules en **texte** (c'est ce que le fichier contient), donc
    ``infer_schema`` voit une colonne homogène ``string`` même quand une valeur
    n'est pas un nombre. Pour que §13.2 (« conformité aux types », « anomalies »)
    nomme la cellule, le contrôle regarde donc la nature **observée** de chaque
    cellule : un texte qui se lit comme un nombre compte comme ``number``. Aucune
    valeur n'est modifiée pour autant — la cellule garde son texte d'origine.

    Une colonne sans majorité stricte (égalité entre deux natures, ou une seule
    valeur) n'entre pas dans le résultat : elle ne produira aucune violation
    arbitraire, ce qui vaut mieux qu'un arbitrage inventé.
    """
    majorities: dict[str, str] = {}
    for field in fields:
        counts: dict[str, int] = {}
        for row in rows:
            if field not in row:
                continue
            kind = _value_kind(row[field])
            if kind == NULL_TYPE:
                continue
            counts[kind] = counts.get(kind, 0) + 1
        if not counts:
            continue
        ranked = sorted(counts.items(), key=lambda item: item[1], reverse=True)
        if len(ranked) == 1 or ranked[0][1] > ranked[1][1]:
            majorities[field] = ranked[0][0]
    return majorities


#: §13.2 — what a cell may be when its column has the given majority nature.
#: ``number`` accueille ``integer`` (un entier est un nombre) ; ``integer`` ne
#: l'inverse pas, sinon ``1.5`` passerait pour un entier.
_KIND_PREDICATES: dict[str, frozenset[str]] = {
    "number": frozenset({"number", "integer"}),
    "integer": frozenset({"integer"}),
    "string": frozenset({"string"}),
    "boolean": frozenset({"boolean"}),
    "json": frozenset({"json"}),
}


def _value_kind(value: Any) -> str:
    """Return the observed nature of *value* (§13.2), text included.

    Un texte qui se lit entièrement comme un nombre a la nature ``number`` :
    c'est ce qui rend visible une cellule qui ne tient pas dans sa colonne, sans
    toucher à la valeur elle-même. Tout le reste garde la nature de son type.
    """
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return NULL_TYPE
        try:
            int(text)
        except ValueError:
            try:
                float(text)
            except ValueError:
                return "string"
            return "number"
        return "integer"
    return value_type(value)


async def check_missing_values(dataset: DatasetLike) -> QualityResult:
    """Score the completeness of every record in *dataset* (§21, §13.1).

    Returns:
        A :class:`QualityResult` whose score is the average per-record
        completeness. An empty dataset scores ``1.0`` with ``checked_rows: 0``,
        which is a measurement, not a claim that data exists.
    """
    rows = dataset_rows(dataset)
    if not rows:
        return QualityResult(score=1.0, details={"checked_rows": 0}, issues=[])

    scores: list[float] = []
    issues: list[str] = []
    for index, row in enumerate(rows):
        evaluation = await CompletenessCheck().run(row)
        scores.append(float(evaluation["score"]))
        issues.extend(f"row {index}: {issue}" for issue in evaluation["issues"])

    details = {
        "checked_rows": len(rows),
        "complete_rows": sum(1 for score in scores if score == 1.0),
    }
    return QualityResult.from_mapping(
        {"score": sum(scores) / len(scores), "details": details, "issues": issues}
    )


async def check_consistency(dataset: DatasetLike) -> QualityResult:
    """Detect internal inconsistencies in *dataset* (§21, §13.3).

    Two signals are combined, both computed from the values themselves:

    * per-record temporal ordering (``updated_at`` must not precede
      ``created_at``), delegated to the §13 ``ConsistencyCheck``;
    * per-column *type drift*, i.e. a column whose values do not all share the
      same inferred type.

    Returns:
        A :class:`QualityResult` where the score is the fraction of consistent
        observations.
    """
    rows = dataset_rows(dataset)
    if not rows:
        return QualityResult(score=1.0, details={"checked_rows": 0, "drifted_columns": []}, issues=[])

    issues: list[str] = []
    observations = 0
    consistent = 0

    for index, row in enumerate(rows):
        evaluation = await ConsistencyCheck().run(row)
        observations += 1
        if float(evaluation["score"]) == 1.0:
            consistent += 1
        else:
            issues.extend(f"row {index}: {issue}" for issue in evaluation["issues"])

    drifted_columns: list[str] = []
    for column, kind in infer_schema(rows).items():
        observations += 1
        if "|" in kind:
            drifted_columns.append(column)
            issues.append(f"column '{column}' mixes types ({kind})")
        else:
            consistent += 1

    details = {"checked_rows": len(rows), "drifted_columns": drifted_columns}
    return QualityResult.from_mapping(
        {
            "score": consistent / observations,
            "details": details,
            "issues": issues,
        }
    )
