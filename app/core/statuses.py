"""§1.3 authorized output statuses and the delivery-status resolution rule.

Before this module the 13 status tokens of §1.3 lived as string literals
scattered across the API layer (``INSUFFICIENT_EVIDENCE``), the request
lifecycle (``PARTIAL_SUCCESS``) and the budget guard
(``BUDGET_EXCEEDED``) — with no place stating the full authorized set.

This module is the single source of truth for:

* :data:`OUTPUT_STATUSES` — the 13 states of §1.3, verbatim;
* :func:`resolve_delivery_status` — the one rule turning what a pipeline
  actually obtained (verified findings, conflicts, staleness, partial
  progress) into one authorized status.

The historical v1 success label ``completed`` is kept as
:data:`PIPELINE_SUCCESS_STATUS` because existing §24.1 deliveries and their
consumers rely on it; :func:`resolve_delivery_status` is the only function
allowed to decide between the two spellings.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from typing import Final

#: §1.3 — every state an INIS output may carry, verbatim and in spec order.
SUCCESS_STATUS: Final[str] = "SUCCESS"
PARTIAL_SUCCESS_STATUS: Final[str] = "PARTIAL_SUCCESS"
INSUFFICIENT_EVIDENCE_STATUS: Final[str] = "INSUFFICIENT_EVIDENCE"
CONFLICTING_SOURCES_STATUS: Final[str] = "CONFLICTING_SOURCES"
SOURCE_UNAVAILABLE_STATUS: Final[str] = "SOURCE_UNAVAILABLE"
SOURCE_STALE_STATUS: Final[str] = "SOURCE_STALE"
ACCESS_DENIED_STATUS: Final[str] = "ACCESS_DENIED"
DATA_INVALID_STATUS: Final[str] = "DATA_INVALID"
TOOL_FAILURE_STATUS: Final[str] = "TOOL_FAILURE"
AGENT_UNAVAILABLE_STATUS: Final[str] = "AGENT_UNAVAILABLE"
TIMEOUT_STATUS: Final[str] = "TIMEOUT"
BUDGET_EXCEEDED_STATUS: Final[str] = "BUDGET_EXCEEDED"
CANCELLED_STATUS: Final[str] = "CANCELLED"

#: The 13 authorized output states of §1.3.
OUTPUT_STATUSES: Final[tuple[str, ...]] = (
    SUCCESS_STATUS,
    PARTIAL_SUCCESS_STATUS,
    INSUFFICIENT_EVIDENCE_STATUS,
    CONFLICTING_SOURCES_STATUS,
    SOURCE_UNAVAILABLE_STATUS,
    SOURCE_STALE_STATUS,
    ACCESS_DENIED_STATUS,
    DATA_INVALID_STATUS,
    TOOL_FAILURE_STATUS,
    AGENT_UNAVAILABLE_STATUS,
    TIMEOUT_STATUS,
    BUDGET_EXCEEDED_STATUS,
    CANCELLED_STATUS,
)

#: Historical v1 delivery label for :data:`SUCCESS_STATUS` (§24.1 consumers).
PIPELINE_SUCCESS_STATUS: Final[str] = "completed"


def resolve_delivery_status(
    *,
    findings: Sequence[Any],
    conflicts: int = 0,
    stale_sources: int = 0,
    partial: bool = False,
) -> str:
    """Return the §1.3 status of a delivery from what the pipeline obtained.

    Args:
        findings: Verified findings kept for delivery (§0.2-compliant ones).
        conflicts: Number of unresolved §14.4 conflicts between the sources
            backing the delivery.
        stale_sources: Number of sources dropped for being §41.5-stale when
            no verified finding could be produced from fresher material.
        partial: ``True`` when the delivery is knowingly incomplete (graceful
            expiry, degraded sub-step) while still carrying verified findings.

    Returns:
        One of :data:`OUTPUT_STATUSES` — except :data:`PIPELINE_SUCCESS_STATUS`,
        the retained v1 spelling of :data:`SUCCESS_STATUS`.

    The precedence follows §14.4 then §1.3: a contradiction between sources is
    reported before any confidence claim, an incomplete-but-evidenced answer is
    ``PARTIAL_SUCCESS``, an empty answer backed by stale-only material is
    ``SOURCE_STALE`` and anything else with no evidence is
    ``INSUFFICIENT_EVIDENCE``.
    """
    if conflicts > 0:
        return CONFLICTING_SOURCES_STATUS
    if findings:
        return PARTIAL_SUCCESS_STATUS if partial else PIPELINE_SUCCESS_STATUS
    if stale_sources > 0:
        return SOURCE_STALE_STATUS
    return INSUFFICIENT_EVIDENCE_STATUS
