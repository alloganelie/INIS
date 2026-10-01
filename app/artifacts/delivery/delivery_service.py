"""Pipeline-facing delivery of the §24.2 artifacts.

:func:`deliver_artifacts` is what :class:`~app.api.v1.requests.pipeline_runner.PipelineRunner`
calls once the run produced its material: it decides whether the request asked
for a *file* (``required_output``), generates it, has it stored, persists its
§24.2 record and returns both the records to publish in the §24.1 ``artifacts``
field and the limitations the delivery must state.

Two rules shape this module:

* **nothing is invented** (§37) — every cell comes from the payload the run
  actually produced; a sheet with no data is written empty and reported;
* **a degradation is named** (§25.2) — ``evidence_package`` produces no file (by
  contract), ``pdf`` cannot be produced (§4.1), an unconfigured object store
  makes the bytes undownloadable, and each case adds one explicit limitation
  instead of failing the delivery.

Known partial (tracked by the conformance plan, lot L3): no ``datasets`` row is
materialised yet, so a ``dataset_export`` artifact is delivered with an empty
``dataset_ids`` and its traceability carried by ``source_ids``. §24.2 accepts any
of the three lineage lists (the domain entity enforces it), and the export stays
auditable through the sources it came from.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.artifacts.generators import FILE_FORMATS, PDF_UNAVAILABLE_REASON, file_formats_message
from app.artifacts.packager.artifact_packager import ArtifactPackager
from app.artifacts.packager.artifact_sequence import InProcessArtifactSequence
from app.core.errors import ValidationError
from app.core.version import API_VERSION
from app.domain.value_objects.request_constraints import DEFAULT_REQUIRED_OUTPUT
from app.storage.object_storage.object_storage_factory import build_object_storage
from app.storage.repositories.artifact_repository import ArtifactRepository
from app.storage.repositories.artifact_version_repository import record_delivered_version
from app.storage.repositories.information_unit_repository import get_database_engine

__all__ = [
    "DATA_COLUMNS",
    "DATA_DICTIONARY",
    "SPREADSHEET_FORMATS",
    "DeliveryOutcome",
    "deliver_artifacts",
    "tabular_projection",
]

#: Formats delivered as a workbook rather than a flat file.
SPREADSHEET_FORMATS: tuple[str, ...] = ("xlsx",)

#: Columns of the §24.3 « données demandées » sheet, in a fixed, documented order.
DATA_COLUMNS: tuple[str, ...] = (
    "information_id",
    "type",
    "source_id",
    "text",
    "language",
    "epistemic_status",
    "data_stage",
    "source_url",
    "retrieved_at",
    "confidence_score",
)

#: §24.3 « dictionnaire de données »: what each column of the data sheet means.
DATA_DICTIONARY: tuple[tuple[str, str], ...] = (
    ("information_id", "Identifiant §11 de l'unité d'information livrée"),
    ("type", "Type de l'unité (§11)"),
    ("source_id", "Source §9 d'où provient l'unité"),
    ("text", "Contenu textuel de l'unité, tel qu'extrait"),
    ("language", "Langue détectée de l'unité"),
    ("epistemic_status", "Statut épistémique (§12) : factual, hypothesis…"),
    ("data_stage", "Étape du cycle de vie (§12) : raw, normalized, enriched, derived"),
    ("source_url", "URL exacte de la source, si connue"),
    ("retrieved_at", "Horodatage d'acquisition de la source"),
    ("confidence_score", "Score de confiance §15 de l'unité"),
)


@dataclass
class DeliveryOutcome:
    """What the delivery produced: the §24.2 records and the caveats."""

    artifacts: list[dict[str, Any]] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    stored: bool = False

    def add_limitation(self, message: str) -> None:
        """Record one §25.2 limitation (never duplicated)."""
        if message not in self.limitations:
            self.limitations.append(message)


#: Sequence used when no database is configured (see the module docstring).
_IN_PROCESS_SEQUENCE = InProcessArtifactSequence()

#: Stated in ``limitations`` whenever the in-process sequence is the allocator.
IN_PROCESS_SEQUENCE_LIMITATION = (
    "Identifiant d'artefact alloué en mémoire (INIS_DATABASE_URL non configuré) : la "
    "séquence §24.2 n'est pas persistée et n'est pas unique entre processus."
)


async def _allocate_artifact_id(engine: Any | None) -> str:
    """Return the next §24.2 identifier, from the database when there is one.

    Raises:
        Exception: Whatever the database raises; the caller turns it into a
            §25.2 limitation, because a delivery that cannot name a file must
            still be delivered (without that file).
    """
    if engine is None:
        return _IN_PROCESS_SEQUENCE.next()
    return await ArtifactRepository.allocate_artifact_id(engine)


def output_format_of(required_output: Any) -> str:
    """Return the §7/§24 delivery format of *required_output*.

    Accepts the API model, the domain dataclass and a plain mapping, so the
    pipeline passes whatever it holds without a conversion layer.

    Args:
        required_output: ``{"format": "json"}``, ``RequiredOutput(...)`` or
            ``None`` (the §7 default, ``evidence_package``).

    Returns:
        The lowercase format name.
    """
    if required_output is None:
        value: Any = None
    elif isinstance(required_output, Mapping):
        value = required_output.get("format")
    else:
        value = getattr(required_output, "format", None)
    return str(value or DEFAULT_REQUIRED_OUTPUT.format).lower()


def tabular_projection(
    information_units: Sequence[Mapping[str, Any]],
    *,
    columns: Sequence[str] = DATA_COLUMNS,
) -> list[dict[str, Any]]:
    """Return the §24.3 « données demandées » rows of the delivered units.

    One row per delivered §11 unit: the closest thing to "the requested data"
    that a run actually produced. A missing field stays empty — §24.3 forbids
    inventing a value.
    """
    rows: list[dict[str, Any]] = []
    for unit in information_units:
        content = unit.get("content")
        provenance = unit.get("provenance")
        confidence = unit.get("confidence")
        content = content if isinstance(content, Mapping) else {}
        provenance = provenance if isinstance(provenance, Mapping) else {}
        confidence = confidence if isinstance(confidence, Mapping) else {}
        rows.append(
            {
                "information_id": unit.get("information_id"),
                "type": unit.get("type"),
                "source_id": unit.get("source_id"),
                "text": content.get("text") or content.get("value") or "",
                "language": unit.get("language"),
                "epistemic_status": unit.get("epistemic_status"),
                "data_stage": unit.get("data_stage"),
                "source_url": provenance.get("url") or provenance.get("extracted_from"),
                "retrieved_at": provenance.get("retrieved_at"),
                "confidence_score": confidence.get("score"),
            }
        )
    return [{column: row.get(column) for column in columns} for row in rows]


def _source_ids(information_units: Sequence[Mapping[str, Any]]) -> list[str]:
    """Return the sorted ``SRC_`` identifiers the delivered units came from."""
    return sorted(
        {
            str(unit.get("source_id"))
            for unit in information_units
            if str(unit.get("source_id") or "").startswith("SRC_")
        }
    )


def _information_ids(information_units: Sequence[Mapping[str, Any]]) -> list[str]:
    """Return the ``INF_`` identifiers of the units the file was built from.

    C'est le maillon « information » de la chaîne
    ``source → transformation → information → artefact`` : les unités livrées
    sont ce qui relie les sources aux octets.
    """
    return list(
        dict.fromkeys(
            str(unit.get("information_id"))
            for unit in information_units
            if str(unit.get("information_id") or "").startswith("INF_")
        )
    )


def _direct_dataset_ids(information_units: Sequence[Mapping[str, Any]]) -> list[str]:
    """Return the ``DATA_`` identifiers the delivered units already name.

    C'est la relation la plus directe : une unité qui dit de quel dataset elle
    vient. Rien n'est fabriqué — une unité sans dataset n'en produit pas.
    """
    return list(
        dict.fromkeys(
            str(unit.get("dataset_id"))
            for unit in information_units
            if str(unit.get("dataset_id") or "").startswith("DATA_")
        )
    )


async def _dataset_ids(
    engine: Any,
    request_id: str,
    information_units: Sequence[Mapping[str, Any]],
) -> list[str]:
    """Return the datasets **really** associated with the delivered units (§24.2).

    Deux relations existantes, et seulement elles :

    * ``information_units.dataset_id`` — l'unité nomme son dataset ;
    * ``datasets.request_id`` **et** ``datasets.source_id ∈ sources des unités
      livrées`` — un dataset créé pour cette requête, dont la source fait partie
      de celles qui ont fourni les unités livrées, a contribué au fichier.

    Aucun identifiant n'est inventé : une requête sans dataset, ou dont les
    datasets ne partagent aucune source avec les unités livrées, obtient une
    liste vide — et le comportement d'avant ce câblage est donc conservé.

    Returns:
        Les identifiants triés et dédoublonnés : un dataset cité par dix unités
        n'apparaît qu'une fois.
    """
    direct = _direct_dataset_ids(information_units)
    if engine is None:
        return sorted(direct)

    from app.storage.repositories.dataset_repository import DatasetRepository

    sources = {
        str(unit.get("source_id"))
        for unit in information_units
        if str(unit.get("source_id") or "").startswith("SRC_")
    }
    related = [
        str(row["dataset_id"])
        for row in await DatasetRepository.list_for_request(engine, request_id)
        if row.get("dataset_id") and str(row.get("source_id")) in sources
    ]
    return sorted({*direct, *related})


def _confidence_score(delivery: Mapping[str, Any]) -> float | None:
    """Return the §15 overall confidence score of *delivery*, when it exists."""
    confidence = delivery.get("confidence")
    if isinstance(confidence, Mapping):
        score = confidence.get("score")
        if isinstance(score, (int, float)):
            return float(score)
    return None


def _joined(values: Sequence[Any]) -> str:
    """Return *values* as a ``;``-separated cell text (empty when none)."""
    return "; ".join(str(value) for value in values if value not in (None, ""))


def _payload_for_file(delivery: Mapping[str, Any]) -> dict[str, Any]:
    """Return the payload written *inside* a JSON or XML artifact.

    The ``artifacts`` field is dropped on purpose: the §24.2 record of a file
    cannot contain the digest of the file that contains it. The record is
    published in the §24.1 response, which is where §24.1 puts it.
    """
    return {key: value for key, value in delivery.items() if key != "artifacts"}


def workbook_sheets(
    *,
    request_id: str,
    delivery: Mapping[str, Any],
    artifact_id: str,
    units_rows: Sequence[Mapping[str, Any]],
    information_units: Sequence[Mapping[str, Any]],
    evidence: Sequence[Mapping[str, Any]],
    sources: Sequence[Mapping[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Return the §24.3 sheets of the workbook export.

    Every sheet is built from material the run actually produced; a dimension the
    delivery does not carry (a unit with no ``quality`` block, for instance) is
    written empty rather than filled with a plausible-looking value (§24.3, §37).
    """
    return {
        "data": [dict(row) for row in units_rows],
        "metadata": [
            {
                "request_id": request_id,
                "response_id": delivery.get("response_id"),
                "status": delivery.get("status"),
                "summary": delivery.get("summary"),
                "findings_count": len(delivery.get("findings") or []),
                "information_units_count": len(information_units),
                "evidence_count": len(evidence),
                "started_at": (delivery.get("timestamps") or {}).get("started_at"),
                "completed_at": (delivery.get("timestamps") or {}).get("completed_at"),
                "generated_at": datetime.now(UTC).isoformat(),
            }
        ],
        "dictionary": [
            {"column": column, "description": description}
            for column, description in DATA_DICTIONARY
        ],
        "sources": [
            {
                "source_id": source.get("source_id"),
                "name": source.get("name"),
                "source_type": source.get("source_type"),
                "trust_level": source.get("trust_level"),
            }
            for source in sources
            if isinstance(source, Mapping)
        ],
        "provenance": [
            {
                "request_id": request_id,
                "pipeline": (delivery.get("provenance") or {}).get("pipeline"),
                "plan_id": (delivery.get("provenance") or {}).get("plan_id"),
                "steps_executed": (delivery.get("provenance") or {}).get("steps_executed"),
                "source_ids": _joined(_source_ids(information_units)),
                "information_ids": _joined(
                    [unit.get("information_id") for unit in information_units]
                ),
                "evidence_ids": _joined(
                    [item.get("evidence_id") for item in evidence if isinstance(item, Mapping)]
                ),
            }
        ],
        "quality": [
            {
                "information_id": unit.get("information_id"),
                "quality_score": (unit.get("quality") or {}).get("score")
                if isinstance(unit.get("quality"), Mapping)
                else None,
                "epistemic_status": unit.get("epistemic_status"),
                "confidence_score": (unit.get("confidence") or {}).get("score")
                if isinstance(unit.get("confidence"), Mapping)
                else None,
            }
            for unit in information_units
        ],
        "version": [
            {
                "artifact_id": artifact_id,
                "format": "xlsx",
                "spec": "§24.3 (export Excel)",
                "api_version": API_VERSION,
                "generated_at": datetime.now(UTC).isoformat(),
            }
        ],
    }


async def deliver_artifacts(
    *,
    request_id: str,
    required_output: Any = None,
    delivery: Mapping[str, Any] | None = None,
    information_units: Sequence[Mapping[str, Any]] = (),
    evidence: Sequence[Mapping[str, Any]] = (),
    sources: Sequence[Mapping[str, Any]] = (),
    storage: Any | None = None,
    file_stem: str | None = None,
) -> DeliveryOutcome:
    """Generate, store and record the artifacts a request asked for (§24).

    Args:
        request_id: The request the files are delivered for.
        required_output: The §7 ``required_output`` (model, dataclass or mapping).
        delivery: The §24.1 payload built so far (minus ``artifacts``).
        information_units: The §11 units the run delivered.
        evidence: The §14.2 evidence the run delivered.
        sources: The §9 sources the run consulted.
        storage: Object-store port; resolved from ``S3_*`` when omitted.
        file_stem: Base name of the file; the request identifier by default, so
            a downloaded file is traceable to its request.

    Returns:
        A :class:`DeliveryOutcome`: the §24.2 records to publish, the §25.2
        limitations to state, and whether the bytes are downloadable.
    """
    outcome = DeliveryOutcome()
    output_format = output_format_of(required_output)

    # §24.1 — ``evidence_package`` *is* the response; no file is attached to it.
    if output_format == "evidence_package":
        return outcome

    # §4.1/§37 — a PDF cannot be produced, and pretending otherwise would be a lie.
    if output_format == "pdf":
        outcome.add_limitation(PDF_UNAVAILABLE_REASON)
        return outcome

    if output_format not in FILE_FORMATS:
        outcome.add_limitation(
            f"Format de livraison inconnu '{output_format}' : aucun artefact généré. "
            f"{file_formats_message()}"
        )
        return outcome

    engine = get_database_engine()
    try:
        artifact_id = await _allocate_artifact_id(engine)
    except Exception as exc:  # noqa: BLE001 - §25.2: a file that cannot be named must not crash the run
        outcome.add_limitation(
            "Aucun artefact généré : allocation de l'identifiant §24.2 impossible "
            f"({type(exc).__name__}: {exc})."
        )
        return outcome
    if engine is None:
        outcome.add_limitation(IN_PROCESS_SEQUENCE_LIMITATION)

    payload = _payload_for_file(delivery or {})
    units_rows = tabular_projection(information_units)
    packager = ArtifactPackager(storage if storage is not None else build_object_storage())

    # §24.2 — les datasets qui ont réellement contribué au fichier, lus depuis les
    # relations existantes (unité → dataset, dataset → source/requête). Une lecture
    # impossible est signalée comme une limite, jamais remplacée par une invention.
    try:
        dataset_ids = await _dataset_ids(engine, request_id, information_units)
    except Exception as exc:  # noqa: BLE001 - §25.2: the gap is reported
        dataset_ids = _direct_dataset_ids(information_units)
        outcome.add_limitation(
            "Datasets du lignage non récupérés depuis la base "
            f"({type(exc).__name__}: {exc}) : seuls ceux que les unités nomment "
            "sont enregistrés."
        )

    try:
        result = packager.package(
            artifact_id=artifact_id,
            output_format=output_format,
            file_stem=file_stem or request_id,
            purpose=(
                f"Livraison du résultat de la demande {request_id} au format "
                f"{output_format} (§24)."
            ),
            payload=payload,
            rows=units_rows,
            columns=DATA_COLUMNS,
            sheets=workbook_sheets(
                request_id=request_id,
                delivery=delivery or {},
                artifact_id=artifact_id,
                units_rows=units_rows,
                information_units=information_units,
                evidence=evidence,
                sources=sources,
            )
            if output_format in SPREADSHEET_FORMATS
            else None,
            source_ids=_source_ids(information_units),
            dataset_ids=dataset_ids,
            transformation_ids=(),
            quality_score=None,
            confidence_score=_confidence_score(delivery or {}),
        )
    except ValidationError as exc:
        outcome.artifacts.clear()
        outcome.add_limitation(f"Aucun artefact {output_format} généré : {exc}")
        return outcome

    record = result.artifact.to_dict()
    record["request_id"] = request_id
    record["created_at"] = datetime.now(UTC).isoformat()
    outcome.artifacts.append(record)
    if result.limitation:
        outcome.add_limitation(result.limitation)
    else:
        outcome.stored = True

    if engine is not None:
        try:
            await ArtifactRepository.create(engine, record)
        except Exception as exc:  # noqa: BLE001 - §25.2: report, never hide
            outcome.add_limitation(
                f"Artefact {artifact_id} non persisté ({type(exc).__name__}: {exc}) — il "
                "reste publié dans la livraison mais n'est pas listable via /v1/artifacts."
            )
        else:
            # §18.1/§24.2 — la version livrée et son lignage sont écrits juste après
            # l'artefact, depuis les mêmes entrées : les informations livrées
            # complètent les sources et transformations que le §24.2 porte déjà.
            try:
                await record_delivered_version(
                    engine,
                    record,
                    information_ids=_information_ids(information_units),
                )
            except Exception as exc:  # noqa: BLE001 - §25.2: report, never hide
                outcome.add_limitation(
                    f"Version/lignage de l'artefact {artifact_id} non enregistrés "
                    f"({type(exc).__name__}: {exc}) — l'historique des versions est incomplet."
                )
    return outcome
