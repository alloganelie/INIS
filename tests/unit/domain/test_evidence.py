"""Tests for the Evidence domain entity."""

import pytest
from pydantic import ValidationError

from app.domain.entities.evidence import Evidence


def make_evidence(**overrides: object) -> Evidence:
    values: dict[str, object] = {
        "evidence_id": "EVID_01H0000000000000000000000",
        "claim_id": None,
        "information_id": "INF_01H00000000000000000000000",
        "document_id": "DOC_01H00000000000000000000000",
        "source_id": "SRC_01H00000000000000000000000",
        "excerpt": "A source-backed excerpt.",
        "location": {"page": 1},
        "strength": 0.8,
    }
    values.update(overrides)
    return Evidence(**values)


def test_evidence_valid_creation() -> None:
    evidence = make_evidence()

    assert evidence.claim_id is None
    assert evidence.strength == 0.8


def test_evidence_accepts_claim_link() -> None:
    evidence = make_evidence(claim_id="CLM_01H00000000000000000000000")

    assert evidence.claim_id == "CLM_01H00000000000000000000000"


def test_evidence_rejects_strength_outside_allowed_range() -> None:
    with pytest.raises(ValidationError):
        make_evidence(strength=1.1)
