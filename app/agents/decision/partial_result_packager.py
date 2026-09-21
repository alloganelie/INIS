"""Create an explicit partial delivery while preserving provenance."""

from dataclasses import dataclass
from typing import Any

from app.core.errors import OutputStatus
from app.domain.entities.information_package import InformationPackage


@dataclass(frozen=True)
class PartialResult:
    """A partial package suitable for progress reporting under §41.1."""

    status: OutputStatus
    package: InformationPackage
    partial_findings_available: bool
    limitations: tuple[str, ...]


class PartialResultPackager:
    """Package available findings without claiming that uncollected data exists."""

    def package(
        self,
        *,
        package_id: str,
        request_id: str,
        units: list[dict[str, Any]],
        confidence: dict[str, Any],
        provenance: dict[str, Any],
        limitations: tuple[str, ...] = (),
    ) -> PartialResult:
        """Return a validated, provenance-bearing partial InformationPackage."""
        information_package = InformationPackage(
            package_id=package_id,
            request_id=request_id,
            units=units,
            confidence=confidence,
            provenance=provenance,
            data_stage="derived",
        )
        information_package.validate()
        return PartialResult(
            status=OutputStatus.PARTIAL_SUCCESS,
            package=information_package,
            partial_findings_available=bool(units),
            limitations=limitations,
        )
