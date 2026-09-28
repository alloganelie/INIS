"""API tests for the §41.12 LLM decision trace endpoint."""

from fastapi.testclient import TestClient

from app.api.v1.requests.pipeline_runner import pipeline_runner
from app.api.v1.requests.router import _REQUESTS_STORE
from app.main import app

client = TestClient(app)


def _create_request(objective: str) -> str:
    res = client.post("/v1/requests", json={"objective": objective})
    assert res.status_code == 201
    return res.json()["request_id"]


def test_llm_traces_endpoint_lists_traces() -> None:
    req_id = _create_request("trace probe: veille énergie solaire")

    res = client.get(f"/v1/requests/{req_id}/llm-traces")
    assert res.status_code == 200
    data = res.json()
    assert data["request_id"] == req_id
    assert data["count"] == len(data["traces"])
    assert data["count"] >= 2, "understanding and planning must both be traced"


def test_llm_traces_follow_the_spec_shape() -> None:
    req_id = _create_request("trace shape probe")
    traces = client.get(f"/v1/requests/{req_id}/llm-traces").json()["traces"]

    for trace in traces:
        for field in (
            "llm_decision_id",
            "request_id",
            "step_id",
            "task_type",
            "model_used",
            "prompt_hash",
            "input_token_count",
            "output_token_count",
            "latency_ms",
            "decision_summary",
            "alternatives_considered",
            "confidence_in_decision",
            "timestamp",
        ):
            assert field in trace, f"missing §41.12 field: {field}"
        assert trace["request_id"] == req_id
        assert trace["step_id"].startswith("STEP_")
        assert len(trace["prompt_hash"]) == 64
        assert 0.0 <= trace["confidence_in_decision"] <= 1.0


def test_llm_traces_cover_understanding_and_planning() -> None:
    req_id = _create_request("trace phases probe")
    traces = client.get(f"/v1/requests/{req_id}/llm-traces").json()["traces"]

    phases = {trace["decision_summary"].split("]")[0].strip("[") for trace in traces}
    assert {"understanding", "planning"} <= phases
    task_types = {trace["task_type"] for trace in traces}
    assert task_types <= {
        "understanding",
        "planning",
        "classification",
        "conflict_detection",
        "confidence_signal",
    }


def test_llm_traces_never_leak_the_prompt_or_the_objective() -> None:
    objective = "secret objective §41.12 leakage probe"
    req_id = _create_request(objective)

    body = client.get(f"/v1/requests/{req_id}/llm-traces").text
    assert objective not in body


def test_llm_traces_are_scoped_to_one_request() -> None:
    first = _create_request("first traced request")
    second = _create_request("second traced request")

    first_traces = pipeline_runner.llm_traces(first)
    second_traces = pipeline_runner.llm_traces(second)
    assert first_traces and second_traces
    assert {t["request_id"] for t in first_traces} == {first}
    assert {t["request_id"] for t in second_traces} == {second}
    # Each request gets its own step ULIDs for the same phases.
    assert set(pipeline_runner.trace_steps(first)) == set(pipeline_runner.trace_steps(second))
    assert (
        pipeline_runner.trace_steps(first)["planning"]
        != pipeline_runner.trace_steps(second)["planning"]
    )


def test_llm_traces_endpoint_404_for_unknown_request() -> None:
    _create_request("store warmup")
    assert "REQ_000000000000000000000000ZZ" not in _REQUESTS_STORE
    res = client.get("/v1/requests/REQ_000000000000000000000000ZZ/llm-traces")
    assert res.status_code == 404
