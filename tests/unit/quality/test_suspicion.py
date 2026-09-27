"""Unit tests for the §41.7 source suspicion (disinformation) module."""

from datetime import datetime
from datetime import timezone

import pytest
from pydantic import ValidationError

from app.domain.entities.source import SourceSuspicion
from app.domain.value_objects.ulid import ULID
from app.quality.suspicion import (
    SUSPICION_WARNING_KEY,
    apply_suspicion_warning,
    assess_editorial_bias,
    assess_source_suspicion,
    content_fingerprint,
    detect_freshness_manipulation,
    detect_mirror,
    detect_synthetic_content,
    lexical_one_sidedness,
    similarity,
    verify_finding_warning,
)

UTC = timezone.utc

#: 5 sentences x 10 words each: perfectly uniform stylometry (cv = 0).
UNIFORM_TEXT = " ".join(
    " ".join(f"w{i}_{j}" for j in range(10)) + "." for i in range(5)
)

#: Varied sentence lengths, no markers — clean human prose (48 words).
CLEAN_TEXT = (
    "The council met on Tuesday morning. "
    "Several residents presented their concerns about the new bridge project "
    "and the expected traffic disruption. "
    "Others supported the plan. "
    "The mayor promised a full environmental review before any construction begins "
    "next spring, with public consultations scheduled across districts. "
    "A vote is due in March."
)


def test_suspicion_config_block_matches_the_spec() -> None:
    payload = SourceSuspicion().to_dict()
    assert set(payload) == {
        "synthetic_content_detected",
        "mirror_of",
        "editorial_bias_score",
        "freshness_manipulation_suspected",
        "suspicion_reason",
    }
    assert payload["synthetic_content_detected"] is False
    assert payload["mirror_of"] is None
    assert payload["suspicion_reason"] is None


def test_suspicion_rejects_invalid_mirror_of() -> None:
    with pytest.raises(ValueError, match="mirror_of"):
        SourceSuspicion(mirror_of="SRC_not-a-ulid")
    with pytest.raises(ValueError, match="mirror_of"):
        SourceSuspicion(mirror_of="DOC_01ARZ3NDEKTSV4RRFFQ69G5FAV")  # wrong prefix
    valid = SourceSuspicion(mirror_of=ULID.new("SRC_"))
    assert valid.mirror_of.startswith("SRC_")


def test_suspicion_warning_and_suspicious_properties() -> None:
    clean = SourceSuspicion()
    assert clean.requires_finding_warning is False
    assert clean.is_suspicious is False

    synthetic = SourceSuspicion(synthetic_content_detected=True)
    assert synthetic.requires_finding_warning is True
    assert synthetic.is_suspicious is True

    biased = SourceSuspicion(editorial_bias_score=0.7)
    assert biased.requires_finding_warning is False
    assert biased.is_suspicious is True


def test_synthetic_detected_from_generator_metadata() -> None:
    detected, reason = detect_synthetic_content(
        CLEAN_TEXT, metadata={"generator": "gpt-4"}
    )
    assert detected is True
    assert "gpt-4" in (reason or "")


def test_synthetic_detected_from_boilerplate_marker() -> None:
    detected, reason = detect_synthetic_content(
        "As an AI language model, I cannot assist with that request."
    )
    assert detected is True
    assert "as an ai" in (reason or "")


def test_synthetic_detected_from_uniform_stylometry() -> None:
    detected, reason = detect_synthetic_content(UNIFORM_TEXT)
    assert detected is True
    assert "uniformity" in (reason or "")


def test_synthetic_detected_from_duplicate_sentences() -> None:
    detected, reason = detect_synthetic_content(
        "Same sentence here. Same sentence here."
    )
    assert detected is True
    assert "consecutive" in (reason or "")


def test_clean_text_is_not_flagged_synthetic() -> None:
    detected, reason = detect_synthetic_content(CLEAN_TEXT)
    assert detected is False
    assert reason is None
    assert detect_synthetic_content("")[0] is False


def test_mirror_exact_copy_is_detected() -> None:
    original_id = ULID.new("SRC_")
    detected = detect_mirror(CLEAN_TEXT, [(original_id, CLEAN_TEXT)])
    assert detected == original_id
    assert content_fingerprint(CLEAN_TEXT) == content_fingerprint(
        CLEAN_TEXT + "  "
    )


def test_mirror_near_copy_is_detected_below_default_threshold() -> None:
    original_id = ULID.new("SRC_")
    near_copy = CLEAN_TEXT + " Extra tail words added."
    detected = detect_mirror(
        near_copy, [(original_id, CLEAN_TEXT)], threshold=0.5
    )
    assert detected == original_id
    assert 0.5 <= similarity(near_copy, CLEAN_TEXT) < 1.0


def test_mirror_returns_none_for_distinct_content() -> None:
    other_id = ULID.new("SRC_")
    different = (
        "Weather patterns across the southern hemisphere remain stable "
        "while ocean temperatures continue their seasonal variation."
    )
    assert detect_mirror(CLEAN_TEXT, [(other_id, different)]) is None
    assert similarity(CLEAN_TEXT, different) < 0.5
    assert detect_mirror(CLEAN_TEXT, []) is None


def test_editorial_bias_score_combines_contradictions_and_lexicon() -> None:
    absolutist = "Always never completely totally certainly definitely always."
    assert lexical_one_sidedness([absolutist]) == 1.0
    balanced = "According to reports it may sometimes vary apparently."
    assert lexical_one_sidedness([balanced]) == 0.0

    assert assess_editorial_bias([absolutist], contradicted_claims=4, total_claims=4) == 1.0
    neutral = ["The report was published in March."]
    assert assess_editorial_bias(neutral, contradicted_claims=2, total_claims=4) == 0.25
    assert assess_editorial_bias([balanced]) == 0.0


def test_editorial_bias_rejects_inconsistent_counts() -> None:
    with pytest.raises(ValueError, match="contradicted_claims"):
        assess_editorial_bias([], contradicted_claims=-1)
    with pytest.raises(ValueError, match="exceed"):
        assess_editorial_bias([], contradicted_claims=5, total_claims=4)


def test_freshness_manipulation_signals() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)

    suspected, reason = detect_freshness_manipulation(
        datetime(2030, 6, 1, tzinfo=UTC), now=now
    )
    assert suspected is True
    assert "future" in (reason or "")

    suspected, reason = detect_freshness_manipulation(
        datetime(2025, 1, 1, tzinfo=UTC),
        content_date=datetime(2020, 1, 1, tzinfo=UTC),
        now=now,
    )
    assert suspected is True
    assert "days newer" in (reason or "")

    suspected, _ = detect_freshness_manipulation(
        datetime(2025, 12, 20, tzinfo=UTC),
        content_date=datetime(2025, 12, 15, tzinfo=UTC),
        now=now,
    )
    assert suspected is False
    assert detect_freshness_manipulation(None, now=now) == (False, None)

    # Naive datetimes are treated as UTC, never compared with mixed offsets.
    suspected, _ = detect_freshness_manipulation(
        datetime(2030, 1, 1), now=datetime(2026, 1, 1)
    )
    assert suspected is True

    with pytest.raises(ValueError, match="tolerance_days"):
        detect_freshness_manipulation(None, tolerance_days=-1)


def test_assess_source_suspicion_clean_source() -> None:
    suspicion = assess_source_suspicion([CLEAN_TEXT])
    assert suspicion.synthetic_content_detected is False
    assert suspicion.mirror_of is None
    assert suspicion.editorial_bias_score == 0.0
    assert suspicion.freshness_manipulation_suspected is False
    assert suspicion.suspicion_reason is None
    assert suspicion.is_suspicious is False


def test_assess_source_suspicion_composes_every_signal() -> None:
    mirrored_id = ULID.new("SRC_")
    suspicion = assess_source_suspicion(
        [CLEAN_TEXT],
        metadata={"generator": "gpt-4"},
        known_sources=[(mirrored_id, CLEAN_TEXT)],
        stated_published_at=datetime(2030, 6, 1, tzinfo=UTC),
        now=datetime(2026, 1, 1, tzinfo=UTC),
    )
    assert suspicion.synthetic_content_detected is True
    assert suspicion.mirror_of == mirrored_id
    assert suspicion.freshness_manipulation_suspected is True
    assert suspicion.suspicion_reason is not None
    assert "; " in suspicion.suspicion_reason
    assert suspicion.requires_finding_warning is True


def test_suspicion_warning_enforces_the_hard_rule() -> None:
    finding = {"statement": "X is true", "source_id": ULID.new("SRC_")}
    synthetic = SourceSuspicion(
        synthetic_content_detected=True,
        suspicion_reason="AI boilerplate marker 'as an ai'",
    )

    # Without the warning the finding must be rejected (§41.7).
    with pytest.raises(ValueError, match="synthetic source"):
        verify_finding_warning(finding, synthetic)

    warned = apply_suspicion_warning(finding, synthetic)
    assert warned[SUSPICION_WARNING_KEY] == "AI boilerplate marker 'as an ai'"
    assert SUSPICION_WARNING_KEY not in finding  # original untouched
    verify_finding_warning(warned, synthetic)

    # A clean source needs no warning at all.
    clean = SourceSuspicion()
    verify_finding_warning(finding, clean)
    assert SUSPICION_WARNING_KEY not in apply_suspicion_warning(finding, clean)

