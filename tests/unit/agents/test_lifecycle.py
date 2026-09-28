"""Unit tests for the resumable request lifecycle per §41.1."""

from datetime import UTC, datetime, timedelta

import pytest

from app.agents.runtime.lifecycle import (
    DEFAULT_TTL_SECONDS,
    GRACEFUL_EXPIRY_STATUS,
    Checkpoint,
    InvalidResumeToken,
    RequestLifecycle,
)

PLAN = [
    "UNDERSTANDING",
    "PLAN_GENERATION",
    "DATA_ACQUISITION",
    "CONFIDENCE",
    "DELIVERY",
]


class FakeClock:
    """Deterministic, manually advanced UTC clock."""

    def __init__(self) -> None:
        self.moment = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.moment

    def advance(self, seconds: int) -> None:
        self.moment += timedelta(seconds=seconds)


def make_lifecycle(**kwargs) -> tuple[RequestLifecycle, FakeClock]:
    """Build a lifecycle wired to a deterministic clock."""
    clock = FakeClock()
    lifecycle = RequestLifecycle(
        "REQ_TEST",
        steps_total=kwargs.pop("steps_total", 5),
        plan=kwargs.pop("plan", PLAN),
        clock=clock,
        **kwargs,
    )
    return lifecycle, clock


def test_lifecycle_starts_receiving_with_full_step_budget() -> None:
    lifecycle, _ = make_lifecycle()
    progress = lifecycle.progress()
    assert progress.steps_total == 5
    assert progress.steps_done == 0
    assert progress.current_step == "RECEIVING"
    assert progress.estimated_completion is not None
    assert progress.partial_findings_available is False
    assert progress.status == "RECEIVING"


def test_commit_step_advances_progress_using_plan_order() -> None:
    lifecycle, _ = make_lifecycle()
    lifecycle.set_step("UNDERSTANDING")
    lifecycle.commit_step("UNDERSTANDING", {"requirements": ["a"]})
    assert lifecycle.progress().steps_done == 1
    lifecycle.commit_step("PLAN_GENERATION")
    assert lifecycle.progress().steps_done == 2


def test_commit_step_is_idempotent() -> None:
    """Replaying the same step after a crash must not double-count."""
    lifecycle, _ = make_lifecycle()
    lifecycle.commit_step("UNDERSTANDING")
    lifecycle.commit_step("UNDERSTANDING")
    assert lifecycle.progress().steps_done == 1


def test_estimated_completion_is_none_when_all_steps_done() -> None:
    lifecycle, _ = make_lifecycle()
    for step in PLAN:
        lifecycle.commit_step(step)
    lifecycle.complete()
    progress = lifecycle.progress()
    assert progress.steps_done == 5
    assert progress.estimated_completion is None
    assert progress.status == "COMPLETED"


def test_partial_findings_flagged_once_a_finding_exists() -> None:
    lifecycle, _ = make_lifecycle()
    assert lifecycle.progress().partial_findings_available is False
    lifecycle.add_finding({"finding": "x", "source_id": "SRC_1", "evidence_id": "EVID_1"})
    assert lifecycle.progress().partial_findings_available is True
    assert lifecycle.partial_findings()[0]["source_id"] == "SRC_1"


def test_resume_state_reports_last_committed_checkpoint() -> None:
    lifecycle, _ = make_lifecycle()
    state = lifecycle.resume_state()
    assert state["resumable"] is False
    assert state["last_committed_step"] is None
    assert state["last_committed_at"] is None
    assert isinstance(state["resume_token"], str)

    lifecycle.commit_step("UNDERSTANDING")
    state = lifecycle.resume_state()
    assert state["resumable"] is True
    assert state["last_committed_step"] == "UNDERSTANDING"
    assert state["last_committed_at"].endswith("Z")


def test_resume_token_is_opaque_and_verifiable() -> None:
    lifecycle, _ = make_lifecycle()
    lifecycle.commit_step("UNDERSTANDING", {"requirements": ["a"]})
    token = lifecycle.issue_resume_token()
    assert "UNDERSTANDING" not in token  # payload is base64url encoded
    payload = lifecycle.verify_resume_token(token)
    assert payload["request_id"] == "REQ_TEST"
    assert payload["step_id"] == "UNDERSTANDING"


def test_resume_token_rejects_tampering() -> None:
    lifecycle, _ = make_lifecycle()
    body, signature = lifecycle.issue_resume_token().split(".", 1)
    with pytest.raises(InvalidResumeToken, match="signature mismatch"):
        lifecycle.verify_resume_token(f"{body}.{signature[:-2]}xx")


def test_resume_token_rejects_foreign_request() -> None:
    """A token issued for another request must not be accepted (§41.1)."""
    secret = b"shared-secret-for-tests"
    source, _ = make_lifecycle(token_secret=secret)
    source.commit_step("UNDERSTANDING")
    other = RequestLifecycle("REQ_OTHER", steps_total=5, token_secret=secret, clock=FakeClock())
    with pytest.raises(InvalidResumeToken, match="another request"):
        other.verify_resume_token(source.issue_resume_token())


def test_resume_token_rejects_expired_token() -> None:
    secret = b"shared-secret-for-tests"
    clock = FakeClock()
    lifecycle = RequestLifecycle("REQ_TEST", steps_total=3, ttl_seconds=10, token_secret=secret, clock=clock)
    lifecycle.commit_step("UNDERSTANDING")
    token = lifecycle.issue_resume_token()
    clock.advance(11)
    with pytest.raises(InvalidResumeToken, match="expired"):
        lifecycle.verify_resume_token(token)


def test_resume_token_rejects_malformed_input() -> None:
    lifecycle, _ = make_lifecycle()
    with pytest.raises(InvalidResumeToken):
        lifecycle.verify_resume_token("not-a-token")
    with pytest.raises(InvalidResumeToken):
        lifecycle.verify_resume_token("!!!.???")


def test_restore_from_token_resumes_after_last_step() -> None:
    secret = b"shared-secret-for-tests"
    source, _ = make_lifecycle(token_secret=secret)
    source.commit_step("UNDERSTANDING", {"requirements": ["a"]})
    source.commit_step("PLAN_GENERATION")
    token = source.issue_resume_token()

    resumed = RequestLifecycle("REQ_TEST", steps_total=5, token_secret=secret, clock=FakeClock())
    checkpoint = resumed.restore_from_token(token)
    assert isinstance(checkpoint, Checkpoint)
    assert checkpoint.step_id == "PLAN_GENERATION"
    assert checkpoint.step_index == 2
    assert resumed.status == "RESUMED"
    assert resumed.progress().steps_done == 2
    # The restored step results travel with the token.
    assert resumed._step_results["UNDERSTANDING"] == {"requirements": ["a"]}


def test_restore_from_token_without_checkpoint_returns_none() -> None:
    secret = b"shared-secret-for-tests"
    source, _ = make_lifecycle(token_secret=secret)
    resumed = RequestLifecycle("REQ_TEST", steps_total=5, token_secret=secret, clock=FakeClock())
    assert resumed.restore_from_token(source.issue_resume_token()) is None


def test_expiry_detection_uses_injected_clock() -> None:
    lifecycle, clock = make_lifecycle(ttl_seconds=60)
    assert lifecycle.is_expired() is False
    clock.advance(59)
    assert lifecycle.is_expired() is False
    clock.advance(2)
    assert lifecycle.is_expired() is True


def test_completed_request_never_expires() -> None:
    lifecycle, clock = make_lifecycle(ttl_seconds=10)
    lifecycle.complete()
    clock.advance(3600)
    assert lifecycle.is_expired() is False


def test_graceful_expiry_returns_partial_success_with_work() -> None:
    """TTL expiry must deliver PARTIAL_SUCCESS instead of losing work."""
    lifecycle, _ = make_lifecycle()
    lifecycle.commit_step("UNDERSTANDING")
    lifecycle.commit_step("PLAN_GENERATION")
    lifecycle.add_finding({"finding": "partial", "source_id": "SRC_1", "evidence_id": "EVID_1"})

    payload = lifecycle.expire_gracefully()
    assert payload["status"] == GRACEFUL_EXPIRY_STATUS == "PARTIAL_SUCCESS"
    assert payload["steps_done"] == 2
    assert payload["last_committed_step"] == "PLAN_GENERATION"
    assert len(payload["findings"]) == 1
    assert payload["resumable"] is True
    assert payload["expired_at"].endswith("Z")


def test_expires_at_is_iso_utc_and_matches_ttl() -> None:
    lifecycle, clock = make_lifecycle(ttl_seconds=DEFAULT_TTL_SECONDS)
    assert lifecycle.expires_at().endswith("Z")
    clock.advance(DEFAULT_TTL_SECONDS)
    assert lifecycle.is_expired() is True


def test_invalid_configuration_is_rejected() -> None:
    with pytest.raises(ValueError, match="steps_total"):
        RequestLifecycle("REQ_X", steps_total=0)
    with pytest.raises(ValueError, match="ttl_seconds"):
        RequestLifecycle("REQ_X", steps_total=1, ttl_seconds=0)
