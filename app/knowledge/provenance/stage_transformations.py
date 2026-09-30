"""§12.1 — one ``Transformation`` per stage a run really executed.

Before this module, a run wrote a **single** ``TRF_`` row with the generic
operator ``PipelineRunner``, no matter what it had actually done (§12.1, C11):
the lineage graph could not tell acquisition from extraction, from synthesis,
from the delivery of a file, and the delivered ``transformations`` field was
hard-coded to ``[]`` (C10).

The four stages of §12 are recorded here — but **only those that ran**:

* ``raw`` — the sources acquired for the request;
* ``normalized`` — the extraction that turned the acquired material into §11 units;
* ``enriched`` — the synthesis that turned the units into traceable findings;
* ``derived`` — the files delivered for the request (§24.2).

A file the request already ingested (§9.1) gets its **own** ``raw``/``normalized``
pair, produced by the §21 reader that read it (``read_csv``…): two producers mean
two rows, and the file's units are never attributed to the extraction of the web
material.

A stage with nothing to show is not recorded: a transformation that claims an
output it never produced would be worse than a missing one (§0.2). Every row
carries the tool that was used, its version, the parameters it received and the
ids it produced, and is validated by the §12.1 entity before leaving this module.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from app.core.version import API_VERSION
from app.domain.entities.transformation import Transformation
from app.domain.value_objects.ulid import ULID

__all__ = ["DATA_STAGES", "build_transformations"]

#: §12 stage order (see ``app/core/constants.py``).
DATA_STAGES: tuple[str, ...] = ("raw", "normalized", "enriched", "derived")


def _unique(values: Sequence[str]) -> list[str]:
    """Return *values* without duplicates and without empty strings."""
    seen: dict[str, None] = {}
    for value in values:
        if value:
            seen[str(value)] = None
    return list(seen)


def _ids(items: Sequence[Any], key: str) -> list[str]:
    """Return the non-empty ``key`` of every mapping of *items*, deduplicated."""
    return _unique(
        str(item[key])
        for item in items
        if isinstance(item, dict) and item.get(key)
    )


def _stage(
    *,
    stage: str,
    request_id: str,
    objective: str,
    input_ids: Sequence[str],
    output_ids: Sequence[str],
    operator: str,
    tool: str,
    tool_version: str | None = None,
    parameters: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Build one validated §12.1 transformation, or ``None`` when it did not run."""
    outputs = [identifier for identifier in output_ids if identifier]
    if not outputs:
        return None
    entity = Transformation(
        transformation_id=ULID.new("TRF_"),
        input_ids=[identifier for identifier in input_ids if identifier],
        output_ids=outputs,
        operator=operator,
        tool=tool,
        tool_version=tool_version or API_VERSION,
        parameters={"stage": stage, "objective": objective, **(parameters or {})},
        result="success",
        justification=f"Étape §12 « {stage} » de la demande {request_id}",
    )
    entity.validate()
    return entity.to_dict()


def build_transformations(
    *,
    request_id: str,
    objective: str,
    sources: Sequence[dict[str, Any]] = (),
    information_units: Sequence[dict[str, Any]] = (),
    evidence: Sequence[dict[str, Any]] = (),
    findings: Sequence[dict[str, Any]] = (),
    artifacts: Sequence[dict[str, Any]] = (),
    model: str | None = None,
    ingested: Mapping[str, Any] | None = None,
    delivered_units: Sequence[dict[str, Any]] = (),
) -> list[dict[str, Any]]:
    """Return the §12.1 transformations of the stages that produced something.

    Args:
        request_id: The request the run belongs to.
        objective: Its objective, kept in ``parameters`` for replay.
        sources: The sources delivered (§9).
        information_units: The §11 units the extraction produced. They are the
            ``normalized`` output — a unit the run synthesised itself must not be
            attributed to the extractor.
        evidence: The §14.2 evidence delivered.
        findings: The verified findings of the delivery.
        artifacts: The §24.2 artifacts delivered.
        model: The LLM model used for the synthesis, when one was called.
        ingested: The material the request ingested (§9.1): ``documents``,
            ``units`` and the ``readers`` that produced them. It is recorded as
            its **own** ``raw``/``normalized`` pair, because the tool that read a
            CSV is not the ``FactExtractor`` that read a web page: one row per
            producer is the truthful lineage, and the file's units are never
            attributed to the extraction of the web material.
        delivered_units: Every unit of the colis, including the ones the run
            synthesised: the ``derived`` stage declares them all as its inputs,
            so a file never contains material its lineage does not mention.

    Returns:
        The transformations, in §12 stage order. A stage with no output of its
        own is **absent** rather than recorded with a fabricated result.
    """
    source_ids = _ids(sources, "source_id")
    unit_ids = _ids(information_units, "information_id")
    delivered_ids = _ids(delivered_units, "information_id") if delivered_units else []
    evidence_ids = _ids(evidence, "evidence_id") or _ids(findings, "evidence_id")
    artifact_ids = _ids(artifacts, "artifact_id")

    material = ingested or {}
    document_ids = _ids(list(material.get("documents") or ()), "document_id")
    ingested_unit_ids = _ids(list(material.get("units") or ()), "information_id")
    readers = sorted(str(reader) for reader in (material.get("readers") or ()))

    candidates = [
        _stage(
            stage="raw",
            request_id=request_id,
            objective=objective,
            input_ids=[request_id],
            output_ids=source_ids,
            operator="ProviderRouter",
            tool="ProviderRouter.search",
            parameters={"sources": len(source_ids)},
        ),
        _stage(
            stage="raw",
            request_id=request_id,
            objective=objective,
            input_ids=[request_id],
            output_ids=document_ids,
            operator="DocumentIngestor",
            tool=", ".join(readers) or "DocumentIngestor",
            parameters={
                "documents": len(document_ids),
                "readers": readers,
                "origin": "uploaded_document",
            },
        ),
        _stage(
            stage="normalized",
            request_id=request_id,
            objective=objective,
            input_ids=source_ids or [request_id],
            output_ids=unit_ids,
            operator="FactExtractor",
            tool="FactExtractor.extract",
            parameters={"information_units": len(unit_ids)},
        ),
        _stage(
            stage="normalized",
            request_id=request_id,
            objective=objective,
            input_ids=document_ids or [request_id],
            output_ids=ingested_unit_ids,
            operator="DocumentIngestor",
            tool="DocumentIngestor.ingest",
            parameters={
                "information_units": len(ingested_unit_ids),
                "origin": "uploaded_document",
            },
        ),
        _stage(
            stage="enriched",
            request_id=request_id,
            objective=objective,
            input_ids=unit_ids or ingested_unit_ids or [request_id],
            output_ids=evidence_ids,
            operator="ModelRouter",
            tool=model or "synthesis",
            parameters={"findings": len(findings), "evidence": len(evidence_ids)},
        ),
        _stage(
            stage="derived",
            request_id=request_id,
            objective=objective,
            input_ids=_unique([*delivered_ids, *unit_ids, *ingested_unit_ids])
            or source_ids
            or [request_id],
            output_ids=artifact_ids,
            operator="ArtifactPackager",
            tool="ArtifactPackager.package",
            parameters={"artifacts": len(artifact_ids)},
        ),
    ]
    return [stage for stage in candidates if stage is not None]
