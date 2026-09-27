"""Unit tests for the §41.2 quota accounting and budget enforcement."""

from datetime import UTC, datetime

import pytest

from app.governance.budget.quotas import (
    BUDGET_EXCEEDED_STATUS,
    COST_UNITS,
    Budget,
    BudgetExceeded,
    BudgetGuard,
    GlobalUsageRegistry,
    UsageReport,
)


def test_cost_units_match_the_seven_defined_by_spec() -> None:
    assert COST_UNITS == (
        "tokens_llm_input",
        "tokens_llm_output",
        "web_requests",
        "api_calls",
        "storage_bytes_written",
        "storage_bytes_read",
        "compute_seconds",
    )


def test_usage_report_defaults_are_zeroed() -> None:
    report = UsageReport(request_id="REQ_1")
    assert report.total_llm_tokens == 0
    assert report.to_dict()["web_requests"] == 0
    assert report.to_dict()["generated_at"].endswith("Z")


def test_usage_report_accumulates_every_unit() -> None:
    report = UsageReport(request_id="REQ_1")
    for unit in COST_UNITS:
        report.add(unit, 2)
    payload = report.to_dict()
    for unit in COST_UNITS:
        assert payload[unit] == 2
    assert payload["total_llm_tokens"] == 4  # input + output


def test_usage_report_rejects_unknown_unit() -> None:
    with pytest.raises(KeyError, match="unknown cost unit"):
        UsageReport(request_id="REQ_1").add("gpu_hours", 1)


def test_usage_report_rejects_negative_amount() -> None:
    with pytest.raises(ValueError, match=">= 0"):
        UsageReport(request_id="REQ_1").add("web_requests", -1)


def test_budget_limit_for_maps_token_dimensions_to_one_limit() -> None:
    budget = Budget(max_llm_tokens=100, max_web_requests=3)
    assert budget.limit_for("tokens_llm_input") == 100
    assert budget.limit_for("tokens_llm_output") == 100
    assert budget.limit_for("web_requests") == 3
    assert budget.limit_for("api_calls") is None


def test_budget_limit_for_rejects_unknown_unit() -> None:
    with pytest.raises(KeyError, match="unknown cost unit"):
        Budget().limit_for("cpu_cycles")


def test_budget_to_dict_exposes_the_config_block() -> None:
    payload = Budget(max_total_cost_usd=2.5).to_dict()
    assert payload["max_total_cost_usd"] == 2.5
    assert payload["max_llm_tokens"] is None


def test_guard_allows_charges_within_budget() -> None:
    guard = BudgetGuard("REQ_1", Budget(max_web_requests=2))
    guard.charge("web_requests")
    guard.charge("web_requests")
    assert guard.report()["status"] == "within_budget"
    assert guard.remaining("web_requests") == 0


def test_guard_raises_budget_exceeded_on_web_limit() -> None:
    guard = BudgetGuard("REQ_1", Budget(max_web_requests=1))
    guard.charge("web_requests")
    with pytest.raises(BudgetExceeded) as excinfo:
        guard.charge("web_requests")
    assert excinfo.value.dimension == "web_requests"
    assert excinfo.value.limit == 1
    assert excinfo.value.consumed == 2
    assert guard.report()["status"] == BUDGET_EXCEEDED_STATUS
    assert guard.report()["exceeded"] == "web_requests"


def test_guard_enforces_shared_llm_token_limit() -> None:
    """max_llm_tokens bounds input + output together."""
    guard = BudgetGuard("REQ_1", Budget(max_llm_tokens=100))
    guard.charge_llm(60, 30)
    with pytest.raises(BudgetExceeded) as excinfo:
        guard.charge_llm(20, 5)
    assert excinfo.value.dimension == "tokens_llm_input"
    assert excinfo.value.consumed == 115


def test_guard_enforces_total_cost_usd() -> None:
    guard = BudgetGuard("REQ_1", Budget(max_total_cost_usd=0.10))
    guard.charge("api_calls", 1, cost_usd=0.05)
    with pytest.raises(BudgetExceeded) as excinfo:
        guard.charge("api_calls", 1, cost_usd=0.10)
    assert excinfo.value.dimension == "total_cost_usd"


def test_guard_enforces_storage_bytes() -> None:
    guard = BudgetGuard("REQ_1", Budget(max_storage_bytes=1000))
    guard.charge("storage_bytes_written", 600)
    with pytest.raises(BudgetExceeded):
        guard.charge("storage_bytes_written", 600)


def test_guard_unbounded_budget_never_raises() -> None:
    guard = BudgetGuard("REQ_1")
    for _ in range(50):
        guard.charge("web_requests")
    assert guard.usage.web_requests == 50
    assert guard.remaining("web_requests") is None


def test_guard_report_contains_budget_and_usage() -> None:
    guard = BudgetGuard("REQ_1", Budget(max_api_calls=5))
    guard.charge("api_calls", 2)
    report = guard.report()
    assert report["request_id"] == "REQ_1"
    assert report["api_calls"] == 2
    assert report["budget"]["max_api_calls"] == 5
    assert set(report) >= {
        "tokens_llm_input",
        "tokens_llm_output",
        "web_requests",
        "api_calls",
        "storage_bytes_written",
        "storage_bytes_read",
        "compute_seconds",
        "total_cost_usd",
    }


def test_global_registry_aggregates_requests() -> None:
    registry = GlobalUsageRegistry()
    first = UsageReport(request_id="REQ_1")
    first.add("web_requests", 3)
    first.add("tokens_llm_input", 10)
    first.total_cost_usd = 0.5
    second = UsageReport(request_id="REQ_2")
    second.add("web_requests", 2)
    second.total_cost_usd = 0.25

    registry.register(first)
    registry.register(second)

    payload = registry.global_report()
    assert payload["request_count"] == 2
    assert payload["web_requests"] == 5
    assert payload["tokens_llm_input"] == 10
    assert payload["total_cost_usd"] == pytest.approx(0.75)
    assert payload["request_ids"] == ["REQ_1", "REQ_2"]


def test_global_registry_get_returns_report() -> None:
    registry = GlobalUsageRegistry()
    report = UsageReport(request_id="REQ_1")
    registry.register(report)
    assert registry.get("REQ_1") is report
    assert registry.get("REQ_UNKNOWN") is None


def test_compute_seconds_derived_from_clock_when_not_set() -> None:
    start = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    report = UsageReport(request_id="REQ_1", started_at=start)
    now = datetime(2026, 1, 1, 12, 0, 30, tzinfo=UTC)
    assert report.to_dict(now=now)["compute_seconds"] == pytest.approx(30.0)
