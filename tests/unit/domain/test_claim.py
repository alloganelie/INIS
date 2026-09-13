"""Tests for the Claim domain entity."""

import pytest
from pydantic import ValidationError

from app.domain.entities.claim import Claim


def make_claim(**overrides: object) -> Claim:
    values: dict[str, object] = {
        "claim_id": "CLM_01H00000000000000000000000",
        "statement": "INIS preserves provenance.",
        "information_ids": ["INF_01H00000000000000000000000"],
        "evidence_ids": ["EVID_01H0000000000000000000000"],
        "confidence": 0.9,
        "epistemic_status": "fact",
    }
    values.update(overrides)
    return Claim(**values)


def test_claim_valid_creation() -> None:
    claim = make_claim()

    assert claim.epistemic_status == "fact"


def test_claim_accepts_non_factual_epistemic_status() -> None:
    claim = make_claim(epistemic_status="hypothesis")

    assert claim.epistemic_status == "hypothesis"


def test_claim_rejects_invalid_confidence() -> None:
    with pytest.raises(ValidationError):
        make_claim(confidence=-0.1)
