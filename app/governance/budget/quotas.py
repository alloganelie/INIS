"""Quota accounting and budget enforcement per §41.2.

The spec fixes ``maximum_cost`` but leaves the measurable units to ``[CONFIG]``.
This module implements exactly the seven units listed by §41.2:

``tokens_llm_input``, ``tokens_llm_output``, ``web_requests``, ``api_calls``,
``storage_bytes_written``, ``storage_bytes_read``, ``compute_seconds``.

Two guarantees matter for correctness:

* **Reportable consumption** — every charged unit ends up in a
  :class:`UsageReport` that is attached to the delivery payload so inter-agent
  billing and drift detection are possible (§41.2).
* **Hard enforcement** — a :class:`BudgetGuard` raises
  :class:`BudgetExceeded` as soon as a dimension is exhausted, so an
  over-budget request stops instead of silently overspending.

Both classes are pure in-memory value objects: no I/O, injectable clock, and
frozen dataclasses so a report can be compared and hashed safely.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any

#: The seven cost units defined by §41.2.
COST_UNITS: tuple[str, ...] = (
    "tokens_llm_input",
    "tokens_llm_output",
    "web_requests",
    "api_calls",
    "storage_bytes_written",
    "storage_bytes_read",
    "compute_seconds",
)

#: Status returned by the pipeline when a budget is exhausted.
BUDGET_EXCEEDED_STATUS = "BUDGET_EXCEEDED"


class BudgetExceeded(RuntimeError):
    """Raised when a request exceeds one of its §41.2 budget dimensions."""

    def __init__(self, dimension: str, limit: float, consumed: float) -> None:
        self.dimension = dimension
        self.limit = limit
        self.consumed = consumed
        super().__init__(
            f"budget exceeded on {dimension}: {consumed} > {limit}"
        )


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _iso_z(moment: datetime) -> str:
    return moment.isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class Budget:
    """Per-dimension budget of a request (``[CONFIG]`` in §41.2).

    Every limit is ``None`` by default, meaning "unbounded" — the spec only
    defines ``maximum_cost`` on the request, so bounds are opt-in.
    """

    max_llm_tokens: int | None = None
    max_web_requests: int | None = None
    max_api_calls: int | None = None
    max_storage_bytes: int | None = None
    max_compute_seconds: int | None = None
    max_total_cost_usd: float | None = None

    def limit_for(self, dimension: str) -> float | None:
        """Return the configured limit for *dimension*, or None if unbounded.

        Raises:
            KeyError: if *dimension* is not a §41.2 unit.
        """
        mapping = {
            "tokens_llm_input": self.max_llm_tokens,
            "tokens_llm_output": self.max_llm_tokens,
            "web_requests": self.max_web_requests,
            "api_calls": self.max_api_calls,
            "storage_bytes_written": self.max_storage_bytes,
            "storage_bytes_read": self.max_storage_bytes,
            "compute_seconds": self.max_compute_seconds,
        }
        if dimension not in mapping:
            raise KeyError(f"unknown cost unit '{dimension}' (expected one of {COST_UNITS})")
        limit = mapping[dimension]
        return float(limit) if limit is not None else None

    def to_dict(self) -> dict[str, Any]:
        """Return the ``budget`` block of the request contract."""
        return {
            "max_llm_tokens": self.max_llm_tokens,
            "max_web_requests": self.max_web_requests,
            "max_api_calls": self.max_api_calls,
            "max_storage_bytes": self.max_storage_bytes,
            "max_compute_seconds": self.max_compute_seconds,
            "max_total_cost_usd": self.max_total_cost_usd,
        }


@dataclass
class UsageReport:
    """Mutable accumulator of the seven §41.2 cost units for one request."""

    request_id: str
    tokens_llm_input: int = 0
    tokens_llm_output: int = 0
    web_requests: int = 0
    api_calls: int = 0
    storage_bytes_written: int = 0
    storage_bytes_read: int = 0
    compute_seconds: float = 0.0
    #: Estimated monetary cost, summed from the LLM router when available.
    total_cost_usd: float = 0.0
    #: Execution start instant, used to derive ``compute_seconds``.
    started_at: datetime = field(default_factory=_utc_now)

    @property
    def total_llm_tokens(self) -> int:
        """Return input + output tokens (bounded by ``max_llm_tokens``)."""
        return self.tokens_llm_input + self.tokens_llm_output

    def add(self, unit: str, amount: float = 1.0) -> None:
        """Charge *amount* to *unit*.

        Raises:
            KeyError: if *unit* is not a §41.2 cost unit.
            ValueError: if *amount* is negative.
        """
        if unit not in COST_UNITS:
            raise KeyError(f"unknown cost unit '{unit}' (expected one of {COST_UNITS})")
        if amount < 0:
            raise ValueError("cost amount must be >= 0")
        setattr(self, unit, getattr(self, unit) + amount)

    def merge(self, other: UsageReport) -> None:
        """Add every unit of *other* into this report (aggregation)."""
        for unit in COST_UNITS:
            self.add(unit, getattr(other, unit))
        self.total_cost_usd += other.total_cost_usd

    def to_dict(self, now: datetime | None = None) -> dict[str, Any]:
        """Return the ``usage_report`` block attached to every delivery."""
        moment = now or _utc_now()
        return {
            "request_id": self.request_id,
            "tokens_llm_input": int(self.tokens_llm_input),
            "tokens_llm_output": int(self.tokens_llm_output),
            "total_llm_tokens": self.total_llm_tokens,
            "web_requests": int(self.web_requests),
            "api_calls": int(self.api_calls),
            "storage_bytes_written": int(self.storage_bytes_written),
            "storage_bytes_read": int(self.storage_bytes_read),
            "compute_seconds": round(
                self.compute_seconds or (moment - self.started_at).total_seconds(), 4
            ),
            "total_cost_usd": round(self.total_cost_usd, 6),
            "generated_at": _iso_z(moment),
        }


@dataclass
class BudgetGuard:
    """Enforce a :class:`Budget` while accumulating a :class:`UsageReport`.

    Usage::

        guard = BudgetGuard("REQ_1", Budget(max_web_requests=2))
        guard.charge("web_requests")   # 1/2
        guard.charge("web_requests")   # 2/2
        guard.charge("web_requests")   # raises BudgetExceeded
    """

    request_id: str
    budget: Budget = field(default_factory=Budget)
    usage: UsageReport = field(init=False)
    exceeded: str | None = None

    def __post_init__(self) -> None:
        self.usage = UsageReport(request_id=self.request_id)

    def charge(self, unit: str, amount: float = 1.0, *, cost_usd: float = 0.0) -> None:
        """Charge *unit* and raise when the corresponding budget is exhausted.

        Raises:
            BudgetExceeded: when the charge crosses a configured limit.
        """
        self.usage.add(unit, amount)
        if cost_usd:
            self.usage.total_cost_usd += cost_usd
        self._enforce(unit)

    def charge_llm(self, input_tokens: int, output_tokens: int, *, cost_usd: float = 0.0) -> None:
        """Charge an LLM call on both token dimensions, sharing one limit."""
        self.usage.add("tokens_llm_input", input_tokens)
        self.usage.add("tokens_llm_output", output_tokens)
        if cost_usd:
            self.usage.total_cost_usd += cost_usd
        self._enforce("tokens_llm_input")
        self._enforce("tokens_llm_output")

    def _enforce(self, unit: str) -> None:
        """Raise when *unit* (or the total cost) crossed its limit."""
        limit = self.budget.limit_for(unit)
        if limit is not None and self._consumed(unit) > limit:
            self.exceeded = unit
            raise BudgetExceeded(unit, limit, float(self._consumed(unit)))

        cost_limit = self.budget.max_total_cost_usd
        if cost_limit is not None and self.usage.total_cost_usd > cost_limit:
            self.exceeded = "total_cost_usd"
            raise BudgetExceeded("total_cost_usd", cost_limit, self.usage.total_cost_usd)

    def _consumed(self, unit: str) -> float:
        """Return the amount consumed for *unit* (tokens share one budget)."""
        if unit.startswith("tokens"):
            return float(self.usage.total_llm_tokens)
        return float(getattr(self.usage, unit))

    def remaining(self, unit: str) -> float | None:
        """Return the remaining allowance for *unit*, or None when unbounded."""
        limit = self.budget.limit_for(unit)
        if limit is None:
            return None
        return max(limit - self._consumed(unit), 0.0)

    def report(self) -> dict[str, Any]:
        """Return the ``usage_report`` payload for this request."""
        payload = self.usage.to_dict()
        payload["budget"] = self.budget.to_dict()
        payload["exceeded"] = self.exceeded
        payload["status"] = BUDGET_EXCEEDED_STATUS if self.exceeded else "within_budget"
        return payload


class GlobalUsageRegistry:
    """Aggregate usage across requests for ``GET /v1/usage/global`` (§41.2)."""

    def __init__(self) -> None:
        self._reports: dict[str, UsageReport] = {}

    def register(self, report: UsageReport) -> None:
        """Store (or replace) the report of a request."""
        self._reports[report.request_id] = report

    def get(self, request_id: str) -> UsageReport | None:
        """Return the report of one request, or None."""
        return self._reports.get(request_id)

    def global_report(self) -> dict[str, Any]:
        """Return the aggregated consumption across every known request."""
        total = UsageReport(request_id="GLOBAL")
        for report in self._reports.values():
            total.merge(report)
        payload = total.to_dict()
        payload["request_count"] = len(self._reports)
        payload["request_ids"] = sorted(self._reports)
        return payload


#: Process-wide registry backing the §41.2 usage endpoints.
GLOBAL_USAGE = GlobalUsageRegistry()
