"""Provenance completeness quality check."""

from typing import Any

from app.quality.checks import QualityResult, quality_result, target_mapping


class ProvenanceCheck:
    """Require traceable provenance metadata for retained information."""

    async def run(self, target: Any) -> QualityResult:
        provenance = target_mapping(target).get("provenance")
        valid = isinstance(provenance, dict) and bool(provenance)
        return quality_result(1.0 if valid else 0.0, {"has_provenance": valid}, [] if valid else ["provenance is missing"])
