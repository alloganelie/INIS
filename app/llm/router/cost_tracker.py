"""Cost Tracker for LLM usage per INIS spec §22 (budgets per §41.2)."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Column, DateTime, Float, Integer, MetaData, String, Table

_METADATA = MetaData()

BUDGET_USAGE_TABLE = Table(
    "budget_usage",
    _METADATA,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("model_id", String(128), nullable=False),
    Column("input_tokens", Integer, nullable=False, default=0),
    Column("output_tokens", Integer, nullable=False, default=0),
    Column("cost_usd", Float, nullable=False, default=0.0),
    Column("recorded_at", DateTime(timezone=True), nullable=False),
)


@dataclass
class UsageEntry:
    """Single LLM usage record pending persistence."""

    model_id: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    recorded_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class CostTracker:
    """Tracks LLM costs by model for budget management per §38."""

    def __init__(self) -> None:
        """Initialize the cost tracker."""
        self._costs: dict[str, float] = defaultdict(float)
        self._pending: list[UsageEntry] = []

    def record_cost(self, model_id: str, cost: float) -> None:
        """Record a cost for a specific model.

        Args:
            model_id: Model identifier.
            cost: Cost in USD.
        """
        if cost < 0:
            raise ValueError("Cost cannot be negative")
        self._costs[model_id] += cost

    def record_usage(
        self,
        model_id: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost_usd: float = 0.0,
    ) -> UsageEntry:
        """Record a per-call usage entry (also feeds the in-memory totals).

        Args:
            model_id: Model identifier.
            input_tokens: Input tokens consumed.
            output_tokens: Output tokens produced.
            cost_usd: Estimated cost in USD.

        Returns:
            The recorded usage entry.
        """
        if input_tokens < 0 or output_tokens < 0:
            raise ValueError("Token counts cannot be negative")
        if cost_usd < 0:
            raise ValueError("Cost cannot be negative")
        entry = UsageEntry(
            model_id=model_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
        )
        self._pending.append(entry)
        self._costs[model_id] += cost_usd
        return entry

    def pending_usage(self) -> list[UsageEntry]:
        """Return usage entries not yet persisted.

        Returns:
            Copy of the pending entries list.
        """
        return list(self._pending)

    def get_total_cost(self, model_id: str) -> float:
        """Get total cost for a specific model.

        Args:
            model_id: Model identifier.

        Returns:
            Total cost in USD.
        """
        return self._costs[model_id]

    def get_all_costs(self) -> dict[str, float]:
        """Get all recorded costs by model.

        Returns:
            Dictionary mapping model IDs to total costs.
        """
        return dict(self._costs)

    def reset(self) -> None:
        """Reset all cost tracking (totals and pending entries)."""
        self._costs.clear()
        self._pending.clear()

    def persist_usage(self, engine: Any) -> int:
        """INSERT pending usage entries into the ``budget_usage`` table.

        The table is created with ``checkfirst`` semantics when missing, so
        no migration is required for local/dev usage (production DDL remains
        owned by ``migrations/``).

        Args:
            engine: SQLAlchemy sync engine (e.g. PostgreSQL or SQLite).

        Returns:
            Number of rows inserted.
        """
        _METADATA.create_all(engine, tables=[BUDGET_USAGE_TABLE], checkfirst=True)
        if not self._pending:
            return 0
        rows = [
            {
                "model_id": entry.model_id,
                "input_tokens": entry.input_tokens,
                "output_tokens": entry.output_tokens,
                "cost_usd": entry.cost_usd,
                "recorded_at": entry.recorded_at,
            }
            for entry in self._pending
        ]
        with engine.begin() as connection:
            connection.execute(BUDGET_USAGE_TABLE.insert(), rows)
        inserted = len(rows)
        self._pending.clear()
        return inserted
