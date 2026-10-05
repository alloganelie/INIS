"""Read-side assembly of the §1/§24.1 InformationPackage (§1, §11, §14.2, §24.1).

The pipeline builds the delivery package in memory and persists its material as
``information_units`` and ``evidence`` rows. Nothing could rebuild the package
from those rows, so a persisted delivery was not re-deliverable: the API knew
what the run had produced, and the database knew the rows, but no component
could go from one to the other.

This repository is that missing bridge. It owns no table of its own: it reads
the two tables the pipeline writes through their own repositories and returns
the §1 ``InformationPackage`` payload, validated by the domain entity so an
empty or provenance-less package is refused instead of delivered.
"""

from __future__ import annotations

from typing import Any, Sequence

from app.core.errors import ValidationError
from app.core.time import utc_now
from app.domain.entities.information_package import InformationPackage
from app.domain.value_objects.ulid import ULID
from app.storage.repositories.evidence_repository import EvidenceRepository
from app.storage.repositories.information_unit_repository import InformationUnitRepository

__all__ = ["InformationPackageRepository"]


class InformationPackageRepository:
    """Assemble a §24.1 delivery package from already-persisted rows."""

    @classmethod
    async def assemble(
        cls,
        engine: Any,
        *,
        request_id: str,
        information_ids: Sequence[str],
        evidence_ids: Sequence[str] = (),
        confidence: dict[str, Any] | None = None,
        data_stage: str = "raw",
    ) -> dict[str, Any]:
        """Return the §1 ``InformationPackage`` for the given persisted rows.

        Args:
            engine: Async SQLAlchemy engine bound to the migrated database.
            request_id: The request the package belongs to.
            information_ids: Identifiers of the persisted §11 units to include.
            evidence_ids: Identifiers of the persisted §14.2 evidence records.
            confidence: The §15 confidence block already computed for the run.
            data_stage: Lifecycle stage of the assembled material (§12).

        Returns:
            The §24.1 package payload: ``package_id``, ``request_id``, ``units``,
            ``evidence``, ``confidence``, ``provenance``, ``data_stage``,
            ``created_at``.

        Raises:
            ValidationError: If no unit of ``information_ids`` is persisted (a
                package with no provenance must not be delivered, §1/§0.2).
        """
        units: list[dict[str, Any]] = []
        for information_id in information_ids:
            unit = await InformationUnitRepository.get(engine, information_id)
            if unit is not None:
                units.append(unit)

        # §1/§0.2 — a package with no unit carries no provenance, so it must be
        # refused here rather than delivered as an empty, unexplainable answer.
        if not units:
            raise ValidationError(
                "InformationPackage requires at least one persisted information unit: "
                f"none of {list(information_ids)} exists."
            )

        evidence: list[dict[str, Any]] = []
        for evidence_id in evidence_ids:
            record = await EvidenceRepository.get(engine, evidence_id)
            if record is not None:
                evidence.append(record)

        source_ids = sorted(
            {
                str(unit.get("source_id"))
                for unit in units
                if unit.get("source_id")
            }
        )

        package = InformationPackage(
            package_id=ULID.new("INF_"),
            request_id=request_id,
            units=units,
            confidence=confidence or {},
            provenance={
                "source_ids": source_ids,
                "information_ids": [unit.get("information_id") for unit in units],
                "pipeline": "InformationPackageRepository",
            },
            created_at=utc_now(),
            data_stage=data_stage,
        )
        # §1 — a package without provenance is refused rather than delivered.
        package.validate()

        payload = package.model_dump(mode="json")
        payload["evidence"] = evidence
        return payload
