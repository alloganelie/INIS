"""§9.1/§11 — what a request already ingested, read back for its delivery.

``POST /v1/requests/{request_id}/documents`` already stores the file, extracts
its §11 units (one per record, one per section) and the ``Dataset`` of a tabular
payload. The pipeline, however, never looked at them: a request whose file had
been ingested delivered an empty ``datasets[]`` and none of that file's units —
the material existed in PostgreSQL and nowhere in the colis (§24.1).

This module reads that material back, and does **only** that: nothing is
re-extracted, nothing is re-stored, and an unreadable database is a stated
limitation rather than an empty delivery presented as a complete one (§25.2).

It is also what makes ``request_type`` operative (§7, C4): the plan can only be
built around a file when the pipeline knows a file was ingested for the request.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.knowledge.ingestion.document_ingestor import reader_for
from app.storage.database.engine import get_default_engine
from app.storage.repositories.dataset_repository import DatasetRepository
from app.storage.repositories.document_repository import DocumentRepository
from app.storage.repositories.information_unit_repository import (
    InformationUnitRepository,
)

__all__ = ["RequestMaterial", "load_request_material", "to_delivery_unit"]

#: §41.13 — an upper bound on the units a single delivery reads back. A file of
#: 100 000 rows must not turn a colis into an unbounded payload.
MAX_MATERIAL_UNITS = 200

#: §11 delivery fields the ``information_units`` table does not store. They are
#: filled with empty values, never with an invented measurement.
_UNIT_DEFAULTS: dict[str, Any] = {
    "unit": None,
    "time": {},
    "classification": {},
    "quality": {},
    "confidence": {"not_a_probability": True},
}


def to_delivery_unit(unit: Mapping[str, Any], request_id: str) -> dict[str, Any]:
    """Return one stored §11 unit in the shape the delivery carries.

    The stored row is the source of truth: this only completes the keys the
    ``information_units`` table does not have (``unit``, ``time``,
    ``classification``, ``quality``, ``confidence``), with empty defaults.
    """
    delivered = dict(unit)
    for key, default in _UNIT_DEFAULTS.items():
        delivered.setdefault(key, dict(default) if isinstance(default, dict) else default)
    context = delivered.get("context")
    context = dict(context) if isinstance(context, Mapping) else {}
    context.setdefault("request_id", request_id)
    delivered["context"] = context
    return delivered


@dataclass(frozen=True)
class RequestMaterial:
    """The §9.1 material a request already ingested."""

    request_id: str
    documents: Sequence[dict[str, Any]] = ()
    datasets: Sequence[dict[str, Any]] = ()
    units: Sequence[dict[str, Any]] = ()
    limitations: Sequence[str] = ()

    @property
    def has_documents(self) -> bool:
        """Return whether the request has at least one ingested document."""
        return bool(self.documents)

    @property
    def has_material(self) -> bool:
        """Return whether anything of the request's ingestion can be delivered."""
        return bool(self.documents or self.datasets or self.units)

    @property
    def readers(self) -> list[str]:
        """Return the §21 readers the ingested documents were read with."""
        return sorted(
            {reader_for(document.get("mime_type")) for document in self.documents}
        )

    def summary(self) -> str:
        """Return the factual sentence describing what was read back.

        Counts only: no unit content, no interpretation. A ``file_ingest`` step
        reports what it found, never what it might mean (§37).
        """
        return (
            f"{len(self.documents)} document(s) ingéré(s) pour la requête, "
            f"{len(self.datasets)} dataset(s), {len(self.units)} unité(s) §11 "
            "relues depuis le stockage (§9.1)."
        )


async def load_request_material(
    request_id: str,
    *,
    engine: Any | None = None,
    max_units: int = MAX_MATERIAL_UNITS,
) -> RequestMaterial:
    """Return the material *request_id* already ingested, never raising.

    Args:
        request_id: The request whose documents are read back.
        engine: Database engine; ``get_default_engine()`` when omitted.
        max_units: Upper bound on the number of units returned (§41.13).

    Returns:
        The documents, datasets and units found, plus the limitations that
        explain anything that could not be read. A database that cannot be read
        yields an empty material **and** a limitation naming the cause.
    """
    target = engine if engine is not None else get_default_engine()
    if target is None:
        return RequestMaterial(
            request_id=request_id,
            limitations=[
                (
                    "Aucun document de la requête n'est relisible (INIS_DATABASE_URL "
                    "non configuré) : l'ingestion d'un fichier téléversé n'est pas "
                    "disponible (§9.1)."
                )
            ],
        )

    limitations: list[str] = []
    try:
        documents = await DocumentRepository.list_for_request(target, request_id)
    except Exception as exc:  # noqa: BLE001 - §25.2: the gap is named, not hidden
        return RequestMaterial(
            request_id=request_id,
            limitations=[
                (
                    f"Documents de la requête illisibles ({type(exc).__name__}: {exc}) — "
                    "aucune unité de fichier n'entre dans le colis (§9.1)."
                )
            ],
        )

    try:
        datasets = await DatasetRepository.list_for_request(target, request_id)
    except Exception as exc:  # noqa: BLE001
        datasets = []
        limitations.append(
            f"Datasets de la requête illisibles ({type(exc).__name__}: {exc})."
        )

    try:
        units = await InformationUnitRepository.list_for_request(
            target, request_id, limit=max_units
        )
    except Exception as exc:  # noqa: BLE001
        units = []
        limitations.append(
            f"Unités §11 de la requête illisibles ({type(exc).__name__}: {exc})."
        )

    if len(units) >= max_units:
        limitations.append(
            f"Seules les {max_units} unités §11 les plus récentes de la requête sont "
            "relues (borne §41.13) : le document en contient davantage."
        )

    return RequestMaterial(
        request_id=request_id,
        documents=list(documents),
        datasets=list(datasets),
        units=[to_delivery_unit(unit, request_id) for unit in units],
        limitations=limitations,
    )
