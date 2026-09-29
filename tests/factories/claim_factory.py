"""Deterministic ``Claim`` builders (§11, §33.2)."""

from __future__ import annotations

from typing import Any

from app.domain.entities.claim import Claim
from app.domain.value_objects.ulid import ULID

#: The statement every default claim asserts.
DEFAULT_STATEMENT = "Paris est la capitale de la France."


def make_claim(
    *,
    information_ids: list[str] | None = None,
    evidence_ids: list[str] | None = None,
    **overrides: Any,
) -> Claim:
    """Return a valid :class:`~app.domain.entities.claim.Claim`.

    Args:
        information_ids: Units backing the claim; a fresh ``INF_`` ULID when
            omitted, so the claim is never traceable to nothing (§0.2).
        evidence_ids: Evidence backing the claim.
        **overrides: Any ``Claim`` field, e.g.
            ``epistemic_status="hypothesis"`` for an unsourced assertion.
    """
    values: dict[str, Any] = {
        "claim_id": ULID.new("CLM_"),
        "statement": DEFAULT_STATEMENT,
        "information_ids": information_ids or [ULID.new("INF_")],
        "evidence_ids": evidence_ids or [ULID.new("EVID_")],
        "confidence": 0.9,
        "epistemic_status": "fact",
    }
    values.update(overrides)
    return Claim(**values)

