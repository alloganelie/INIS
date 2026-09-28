"""Unit tests for §41.2 budget enforcement and usage accounting.

The §41.2 enforcer is implemented in :mod:`app.governance.budget.quotas`
(``BudgetGuard`` / ``Budget`` / ``UsageReport``); this module pins both
guarantees of the spec: every charge is **reported** and a configured limit is
**enforced** by raising ``BudgetExceeded``.
"""

from __future__ import annotations

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


class TestBudgetDimensions:
    """§41.2 — the seven cost units and their limits."""

    def test_seven_cost_units_are_defined(self) -> None:
        """The spec's seven units are the only accepted ones."""
        assert COST_UNITS == (
            "tokens_llm_input",
            "tokens_llm_output",
            "web_requests",
            "api_calls",
            "storage_bytes_written",
            "storage_bytes_read",
            "compute_seconds",
        )

    def test_unbounded_by_default(self) -> None:
        """Nothing is bounded unless the request asked for it."""
        for unit in COST_UNITS:
            assert Budget().limit_for(unit) is None

    def test_limits_are_exposed_per_dimension(self) -> None:
        """Token and storage limits are shared by their two dimensions."""
        budget = Budget(
            max_llm_tokens=1000,
            max_web_requests=3,
            max_api_calls=10,
            max_storage_bytes=2048,
            max_compute_seconds=60,
            max_total_cost_usd=1.5,
        )
        assert budget.limit_for("tokens_llm_input") == 1000.0
        assert budget.limit_for("tokens_llm_output") == 1000.0
        assert budget.limit_for("web_requests") == 3.0
        assert budget.limit_for("api_calls") == 10.0
        assert budget.limit_for("storage_bytes_written") == 2048.0
        assert budget.limit_for("storage_bytes_read") == 2048.0
        assert budget.limit_for("compute_seconds") == 60.0

    def test_unknown_dimension_is_a_key_error(self) -> None:
        """A typo must not be treated as "unbounded"."""
        with pytest.raises(KeyError):
            Budget().limit_for("web_request")

    def test_to_dict_exposes_every_limit(self) -> None:
        """The ``budget`` block of the request contract is complete."""
        assert set(Budget(max_api_calls=1).to_dict()) == {
            "max_llm_tokens",
            "max_web_requests",
            "max_api_calls",
            "max_storage_bytes",
            "max_compute_seconds",
            "max_total_cost_usd",
        }


class TestUsageReport:
    """§41.2 — consumption is reportable."""

    def test_add_accumulates_a_unit(self) -> None:
        """Charging twice adds up."""
        report = UsageReport(request_id="REQ_1")
        report.add("web_requests", 1)
        report.add("web_requests", 2)
        assert report.web_requests == 3

    def test_unknown_unit_is_refused(self) -> None:
        """Only §41.2 units can be charged."""
        with pytest.raises(KeyError):
            UsageReport(request_id="REQ_1").add("gpu_seconds")

    def test_negative_amount_is_refused(self) -> None:
        """Consumption can never decrease."""
        with pytest.raises(ValueError):
            UsageReport(request_id="REQ_1").add("api_calls", -1)

    def test_total_llm_tokens_sums_both_directions(self) -> None:
        """``total_llm_tokens`` is input + output."""
        report = UsageReport(request_id="REQ_1")
        report.add("tokens_llm_input", 120)
        report.add("tokens_llm_output", 80)
        assert report.total_llm_tokens == 200

    def test_merge_aggregates_two_reports(self) -> None:
        """``merge`` supports the global aggregation endpoint."""
        first = UsageReport(request_id="REQ_1", web_requests=2, total_cost_usd=0.5)
        second = UsageReport(request_id="REQ_2", web_requests=1, total_cost_usd=0.25)
        first.merge(second)
        assert first.web_requests == 3
        assert first.total_cost_usd == 0.75

    def test_to_dict_is_the_delivery_block(self) -> None:
        """The serialized report names the request and every unit."""
        report = UsageReport(request_id="REQ_1")
        report.add("compute_seconds", 1.5)
        payload = report.to_dict()
        assert payload["request_id"] == "REQ_1"
        assert payload["compute_seconds"] == 1.5
        assert set(COST_UNITS) <= set(payload)


class TestBudgetGuardEnforcement:
    """§41.2 — a configured limit is a hard stop."""

    def test_charge_within_limit_passes(self) -> None:
        """Charging up to the limit is allowed (``== limit`` is not a breach)."""
        guard = BudgetGuard("REQ_1", Budget(max_web_requests=2))
        guard.charge("web_requests")
        guard.charge("web_requests")
        assert guard.usage.web_requests == 2
        assert guard.exceeded is None

    def test_charge_beyond_limit_raises(self) -> None:
        """The third request breaches ``max_web_requests=2``."""
        guard = BudgetGuard("REQ_1", Budget(max_web_requests=2))
        guard.charge("web_requests")
        guard.charge("web_requests")
        with pytest.raises(BudgetExceeded) as excinfo:
            guard.charge("web_requests")
        assert excinfo.value.dimension == "web_requests"
        assert excinfo.value.limit == 2
        assert excinfo.value.consumed == 3

    def test_zero_limit_denies_the_first_charge(self) -> None:
        """``max_web_requests=0`` means "no outbound request at all"."""
        guard = BudgetGuard("REQ_1", Budget(max_web_requests=0))
        with pytest.raises(BudgetExceeded):
            guard.charge("web_requests")

    def test_exceeded_dimension_is_recorded(self) -> None:
        """The breached dimension survives for the delivery payload."""
        guard = BudgetGuard("REQ_1", Budget(max_api_calls=1))
        guard.charge("api_calls")
        with pytest.raises(BudgetExceeded):
            guard.charge("api_calls")
        assert guard.exceeded == "api_calls"

    def test_llm_tokens_share_one_limit(self) -> None:
        """Input + output tokens are billed against ``max_llm_tokens``."""
        guard = BudgetGuard("REQ_1", Budget(max_llm_tokens=100))
        guard.charge_llm(60, 30)
        assert guard.usage.total_llm_tokens == 90
        with pytest.raises(BudgetExceeded) as excinfo:
            guard.charge_llm(20, 0)
        assert excinfo.value.dimension == "tokens_llm_input"

    def test_total_cost_limit_is_enforced(self) -> None:
        """``max_total_cost_usd`` is checked alongside the unit limits."""
        guard = BudgetGuard("REQ_1", Budget(max_total_cost_usd=0.10))
        guard.charge("api_calls", cost_usd=0.05)
        with pytest.raises(BudgetExceeded) as excinfo:
            guard.charge("api_calls", cost_usd=0.10)
        assert excinfo.value.dimension == "total_cost_usd"
        assert guard.exceeded == "total_cost_usd"

    def test_remaining_reports_the_allowance(self) -> None:
        """``remaining`` decreases and never goes negative."""
        guard = BudgetGuard("REQ_1", Budget(max_web_requests=3))
        guard.charge("web_requests")
        assert guard.remaining("web_requests") == 2.0
        assert guard.remaining("api_calls") is None

    def test_unbounded_dimension_never_raises(self) -> None:
        """A dimension without a limit is never a breach."""
        guard = BudgetGuard("REQ_1")
        for _ in range(50):
            guard.charge("api_calls")
        assert guard.exceeded is None


class TestGuardReport:
    """§41.2 — the ``usage_report`` attached to every delivery."""

    def test_within_budget_report(self) -> None:
        """A compliant run reports ``within_budget``."""
        guard = BudgetGuard("REQ_1", Budget(max_web_requests=5))
        guard.charge("web_requests")
        report = guard.report()
        assert report["status"] == "within_budget"
        assert report["exceeded"] is None
        assert report["request_id"] == "REQ_1"

    def test_exceeded_report(self) -> None:
        """A breached run reports ``BUDGET_EXCEEDED`` and the dimension."""
        guard = BudgetGuard("REQ_1", Budget(max_web_requests=0))
        with pytest.raises(BudgetExceeded):
            guard.charge("web_requests")
        report = guard.report()
        assert report["status"] == BUDGET_EXCEEDED_STATUS
        assert report["exceeded"] == "web_requests"
        assert report["web_requests"] == 1

    def test_report_embeds_the_budget_block(self) -> None:
        """Consumers see both the consumption and the configured limits."""
        guard = BudgetGuard("REQ_1", Budget(max_api_calls=2))
        guard.charge("api_calls")
        assert guard.report()["budget"]["max_api_calls"] == 2


class TestGlobalUsageRegistry:
    """§41.2 — ``GET /v1/usage/global`` aggregation."""

    def test_registry_aggregates_requests(self) -> None:
        """Totals and request count span every registered report."""
        registry = GlobalUsageRegistry()
        registry.register(UsageReport(request_id="REQ_1", web_requests=2))
        registry.register(UsageReport(request_id="REQ_2", web_requests=3))
        payload = registry.global_report()
        assert payload["web_requests"] == 5
        assert payload["request_count"] == 2
        assert payload["request_ids"] == ["REQ_1", "REQ_2"]

    def test_register_replaces_a_request_report(self) -> None:
        """Re-registering a request overwrites its previous report."""
        registry = GlobalUsageRegistry()
        registry.register(UsageReport(request_id="REQ_1", web_requests=1))
        registry.register(UsageReport(request_id="REQ_1", web_requests=4))
        assert registry.get("REQ_1").web_requests == 4
        assert registry.global_report()["request_count"] == 1

    def test_unknown_request_returns_none(self) -> None:
        """An unknown request id is not an error."""
        assert GlobalUsageRegistry().get("REQ_missing") is None

    def test_empty_registry_reports_zero(self) -> None:
        """Nothing registered yet → zero consumption."""
        payload = GlobalUsageRegistry().global_report()
        assert payload["request_count"] == 0
        assert payload["web_requests"] == 0

