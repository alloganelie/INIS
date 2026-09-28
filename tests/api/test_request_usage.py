"""API tests for the §41.2 usage endpoints and BUDGET_EXCEEDED delivery."""

import pytest
from fastapi.testclient import TestClient

from app.api.v1.requests.pipeline_runner import pipeline_runner
from app.main import app

client = TestClient(app)


def test_usage_endpoint_returns_all_seven_units() -> None:
    res = client.post("/v1/requests", json={"objective": "usage probe"})
    req_id = res.json()["request_id"]

    usage = client.get(f"/v1/requests/{req_id}/usage")
    assert usage.status_code == 200
    data = usage.json()
    for unit in (
        "tokens_llm_input",
        "tokens_llm_output",
        "web_requests",
        "api_calls",
        "storage_bytes_written",
        "storage_bytes_read",
        "compute_seconds",
    ):
        assert unit in data, f"missing §41.2 unit: {unit}"
    assert data["request_id"] == req_id
    assert "budget" in data
    assert "status" in data


def test_usage_endpoint_counts_charges() -> None:
    res = client.post("/v1/requests", json={"objective": "charge probe"})
    req_id = res.json()["request_id"]
    before = client.get(f"/v1/requests/{req_id}/usage").json()
    pipeline_runner.charge(req_id, "web_requests", 3)
    pipeline_runner.charge(req_id, "api_calls", 2)

    data = client.get(f"/v1/requests/{req_id}/usage").json()
    assert data["web_requests"] == before["web_requests"] + 3
    assert data["api_calls"] == before["api_calls"] + 2


def test_usage_endpoint_404_for_unknown_request() -> None:
    res = client.get("/v1/requests/REQ_00000000000000000000000000/usage")
    assert res.status_code == 404


def test_global_usage_aggregates_all_requests() -> None:
    res = client.get("/v1/usage/global")
    assert res.status_code == 200
    data = res.json()
    assert "request_count" in data
    assert "web_requests" in data
    assert "total_cost_usd" in data
    assert data["request_count"] >= 0


def test_budget_is_accepted_in_request_contract() -> None:
    res = client.post(
        "/v1/requests",
        json={
            "objective": "budgeted request",
            "budget": {"max_web_requests": 1, "max_llm_tokens": 100},
        },
    )
    assert res.status_code == 201
    req_id = res.json()["request_id"]
    data = client.get(f"/v1/requests/{req_id}/usage").json()
    assert data["budget"]["max_web_requests"] == 1
    assert data["budget"]["max_llm_tokens"] == 100


def test_breached_budget_reports_budget_exceeded_status() -> None:
    """A request whose web budget is exhausted must say so explicitly (§41.2)."""
    from app.governance.budget.quotas import Budget, BudgetExceeded

    req_id = "REQ_BUDGET_TEST"
    pipeline_runner.guard_for(req_id, Budget(max_web_requests=0))
    with pytest.raises(BudgetExceeded) as excinfo:
        pipeline_runner.charge(req_id, "web_requests")
    assert excinfo.value.dimension == "web_requests"

    report = pipeline_runner.usage_report(req_id)
    assert report["status"] == "BUDGET_EXCEEDED"
    assert report["exceeded"] == "web_requests"
