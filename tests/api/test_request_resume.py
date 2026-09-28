"""API tests for the §41.1 resume and graceful-expiry endpoints."""

from fastapi.testclient import TestClient

from app.api.v1.requests.pipeline_runner import pipeline_runner
from app.main import app

client = TestClient(app)


def _create_request() -> str:
    res = client.post("/v1/requests", json={"objective": "Long running study"})
    assert res.status_code == 201
    return res.json()["request_id"]


def _interrupt(request_id: str, steps: list[str]) -> None:
    """Simulate a crash: start a new attempt and commit the listed steps."""
    lifecycle = pipeline_runner.begin_attempt(request_id)
    for index, step in enumerate(steps, start=1):
        lifecycle.commit_step(step, {"index": index})


def test_resume_state_exposes_opaque_token() -> None:
    req_id = _create_request()
    res = client.get(f"/v1/requests/{req_id}/resume")
    assert res.status_code == 200
    data = res.json()
    assert set(data) == {"resumable", "last_committed_step", "last_committed_at", "resume_token"}
    assert data["resumable"] is False
    assert data["resume_token"]


def test_resume_state_reflects_committed_steps() -> None:
    req_id = _create_request()
    _interrupt(req_id, ["UNDERSTANDING"])
    data = client.get(f"/v1/requests/{req_id}/resume").json()
    assert data["resumable"] is True
    assert data["last_committed_step"] == "UNDERSTANDING"
    assert data["last_committed_at"].endswith("Z")


def test_resume_endpoint_restores_last_committed_step() -> None:
    req_id = _create_request()
    _interrupt(req_id, ["UNDERSTANDING", "PLAN_GENERATION"])
    token = client.get(f"/v1/requests/{req_id}/resume").json()["resume_token"]

    res = client.post(f"/v1/requests/{req_id}/resume", json={"resume_token": token})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "resumed"
    assert data["last_committed_step"] == "PLAN_GENERATION"
    assert data["resumable"] is True
    assert data["steps_done"] == 2


def test_resume_does_not_restart_completed_work() -> None:
    """After resume, progress continues from the checkpoint (no double-count)."""
    req_id = _create_request()
    _interrupt(req_id, ["UNDERSTANDING", "PLAN_GENERATION"])
    token = client.get(f"/v1/requests/{req_id}/resume").json()["resume_token"]
    client.post(f"/v1/requests/{req_id}/resume", json={"resume_token": token})

    progress = client.get(f"/v1/requests/{req_id}/progress").json()
    assert progress["steps_done"] == 2


def test_resume_rejects_invalid_token_with_400() -> None:
    req_id = _create_request()
    res = client.post(
        f"/v1/requests/{req_id}/resume",
        json={"resume_token": "forged.token"},
    )
    assert res.status_code == 400
    assert "resume token" in res.json()["detail"]


def test_resume_rejects_tampered_token_with_400() -> None:
    req_id = _create_request()
    _interrupt(req_id, ["UNDERSTANDING"])
    token = client.get(f"/v1/requests/{req_id}/resume").json()["resume_token"]
    body, signature = token.split(".", 1)
    res = client.post(
        f"/v1/requests/{req_id}/resume",
        json={"resume_token": f"{body}.{signature[:-3]}zzz"},
    )
    assert res.status_code == 400


def test_resume_requires_existing_request() -> None:
    res = client.post(
        "/v1/requests/REQ_00000000000000000000000000/resume",
        json={"resume_token": "abcdefgh.ijklmnop"},
    )
    assert res.status_code == 404


def test_expire_endpoint_returns_partial_success() -> None:
    """A TTL-expired request must deliver PARTIAL_SUCCESS, not silence."""
    req_id = _create_request()
    lifecycle = pipeline_runner.begin_attempt(req_id)
    lifecycle.commit_step("UNDERSTANDING")
    lifecycle.add_finding(
        {"finding": "partial", "source_id": "SRC_1", "evidence_id": "EVID_1"}
    )

    res = client.post(f"/v1/requests/{req_id}/expire")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "PARTIAL_SUCCESS"
    assert data["steps_done"] == 1
    assert data["last_committed_step"] == "UNDERSTANDING"
    assert len(data["findings"]) == 1


def test_expired_request_progress_reports_partial_success() -> None:
    req_id = _create_request()
    lifecycle = pipeline_runner.begin_attempt(req_id, steps_total=3)
    lifecycle.commit_step("UNDERSTANDING")
    lifecycle.force_expiry()

    res = client.get(f"/v1/requests/{req_id}/progress")
    assert res.status_code == 200
    assert res.json()["current_step"] == "PARTIAL_SUCCESS"
