"""§41.1 scenario — « reprise après crash ».

When the process dies mid-request the committed steps survive in the §41.1
lifecycle: the request exposes an *opaque* resume token, resuming restores the
last committed step without double-counting, replaying a step after the crash
is idempotent, a forged or foreign token never replaces live state, and a TTL
expiry hands back ``PARTIAL_SUCCESS`` with the partial findings instead of
silence.

In-process only — no Docker, no network.
"""

from __future__ import annotations

import pytest

from app.agents.runtime.lifecycle import GRACEFUL_EXPIRY_STATUS, InvalidResumeToken
from app.api.v1.requests.pipeline_runner import PIPELINE_STEPS_TOTAL, PipelineRunner

CRASHED_STEPS = ["UNDERSTANDING", "PLAN_GENERATION"]


def _crash_after(runner: PipelineRunner, request_id: str, steps: list[str]) -> None:
    """Simulate a run that dies after committing *steps* (nothing else runs)."""
    lifecycle = runner.begin_attempt(request_id)
    for index, step in enumerate(steps, start=1):
        lifecycle.commit_step(step, {"index": index})


def test_crashed_request_exposes_an_opaque_resume_token() -> None:
    """The checkpoint left by the crash carries an opaque, tamper-proof token (§41.1)."""
    runner = PipelineRunner()
    _crash_after(runner, "REQ_CRASH", CRASHED_STEPS)

    state = runner.resume_state("REQ_CRASH")
    assert state is not None
    assert state["resumable"] is True
    assert state["last_committed_step"] == "PLAN_GENERATION"

    token = state["resume_token"]
    assert token.count(".") == 1, "the token is '<payload>.<signature>'"
    for step in CRASHED_STEPS:
        assert step not in token, "an opaque token must not leak plaintext state"


def test_resume_continues_after_the_last_committed_step() -> None:
    """Resuming restores the checkpoint and restarts the attempt from it (§41.1)."""
    runner = PipelineRunner()
    _crash_after(runner, "REQ_CRASH", CRASHED_STEPS)
    token = runner.resume_state("REQ_CRASH")["resume_token"]

    result = runner.resume("REQ_CRASH", token)

    assert result["status"] == "resumed"
    assert result["last_committed_step"] == "PLAN_GENERATION"
    assert result["steps_done"] == 2
    assert result["steps_total"] == PIPELINE_STEPS_TOTAL
    assert runner.get_state("REQ_CRASH")["status"] == "resumed"
    assert runner.get_state("REQ_CRASH")["resumed_from_step"] == "PLAN_GENERATION"
    assert any(
        event.get("step") == "resumed"
        for event in runner._event_history.get("REQ_CRASH", [])
    ), "the resume is an observable event, not a silent state swap"
    assert runner.get_lifecycle("REQ_CRASH").status == "RESUMED"
    assert runner.progress("REQ_CRASH").steps_done == 2


def test_replayed_step_after_resume_does_not_double_count() -> None:
    """Replaying the committed step the crash interrupted must be idempotent."""
    runner = PipelineRunner()
    _crash_after(runner, "REQ_CRASH", CRASHED_STEPS)
    token = runner.resume_state("REQ_CRASH")["resume_token"]
    runner.resume("REQ_CRASH", token)

    # The crash replayed its last commit: same step id → same checkpoint.
    runner.commit_step("REQ_CRASH", "PLAN_GENERATION")
    assert runner.progress("REQ_CRASH").steps_done == 2, "no double-count on replay"

    # Work then genuinely continues after the checkpoint.
    runner.commit_step("REQ_CRASH", "DATA_ACQUISITION")
    assert runner.progress("REQ_CRASH").steps_done == 3


def test_foreign_or_forged_token_never_replaces_live_state() -> None:
    """A token issued for another request (or tampered) fails closed (§41.1)."""
    runner = PipelineRunner()
    _crash_after(runner, "REQ_A", CRASHED_STEPS)
    _crash_after(runner, "REQ_B", ["UNDERSTANDING"])
    token_a = runner.resume_state("REQ_A")["resume_token"]

    with pytest.raises(InvalidResumeToken):
        runner.resume("REQ_B", token_a)
    # REQ_B state is untouched by the rejected attempt.
    assert runner.resume_state("REQ_B")["last_committed_step"] == "UNDERSTANDING"
    assert runner.get_lifecycle("REQ_B").status != "RESUMED"

    body, signature = token_a.split(".", 1)
    with pytest.raises(InvalidResumeToken):
        runner.resume("REQ_A", f"{body}.{signature[:-3]}zzz")
    with pytest.raises(InvalidResumeToken):
        runner.resume("REQ_A", "forged.token")


def test_ttl_expiry_delivers_partial_success_instead_of_losing_work() -> None:
    """A request that dies past its TTL exposes PARTIAL_SUCCESS + its findings."""
    runner = PipelineRunner()
    lifecycle = runner.begin_attempt("REQ_TTL")
    lifecycle.commit_step("UNDERSTANDING", {"index": 1})
    finding = {"finding": "partiel", "source_id": "SRC_1", "evidence_id": "EVID_1"}
    lifecycle.add_finding(finding)
    lifecycle.force_expiry()

    payload = runner.collect_expired("REQ_TTL")

    assert payload is not None
    assert payload["status"] == GRACEFUL_EXPIRY_STATUS == "PARTIAL_SUCCESS"
    assert payload["steps_done"] == 1
    assert payload["last_committed_step"] == "UNDERSTANDING"
    assert payload["findings"] == [finding]
    assert payload["resumable"] is True
