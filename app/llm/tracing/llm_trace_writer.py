"""LLM decision trace writer per INIS spec §41.12.

Every significant LLM call (understanding, planning, classification, …)
must produce an ``llm_decision_trace``. Traces are always kept in memory
and can optionally be persisted to the ``llm_decision_trace`` table (created
with ``checkfirst`` semantics; production DDL remains owned by
``migrations/``).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Column, DateTime, Float, Integer, MetaData, String, Table, Text
from ulid import ULID as UlidFactory

from app.core.errors import ValidationError

_METADATA = MetaData()

TASK_TYPES = frozenset(
    {
        "understanding",
        "planning",
        "classification",
        "conflict_detection",
        "confidence_signal",
    }
)

REQUIRED_FIELDS = frozenset(
    {
        "request_id",
        "step_id",
        "task_type",
        "model_used",
        "prompt_hash",
    }
)

LLM_DECISION_TRACE_TABLE = Table(
    "llm_decision_trace",
    _METADATA,
    Column("llm_decision_id", String(64), primary_key=True),
    Column("request_id", String(64), nullable=False),
    Column("step_id", String(64), nullable=False),
    Column("task_type", String(32), nullable=False),
    Column("model_used", String(128), nullable=False),
    Column("prompt_hash", String(64), nullable=False),
    Column("input_token_count", Integer, nullable=False, default=0),
    Column("output_token_count", Integer, nullable=False, default=0),
    Column("latency_ms", Integer, nullable=False, default=0),
    Column("decision_summary", Text, nullable=False, default=""),
    Column("alternatives_considered", Text, nullable=False, default="[]"),
    Column("confidence_in_decision", Float, nullable=False, default=0.0),
    Column("timestamp", DateTime(timezone=True), nullable=False),
)


def hash_prompt(prompt: str) -> str:
    """Return the sha256 hex digest of a prompt (never stores clear text)."""
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


class LLMTraceWriter:
    """Records ``llm_decision_trace`` entries in memory, persist optionally."""

    def __init__(self, engine: Any | None = None) -> None:
        """Initialize the writer, optionally bound to a SQLAlchemy engine."""
        self._engine = engine
        self._traces: list[dict[str, Any]] = []

    @staticmethod
    def build_trace(
        request_id: str,
        step_id: str,
        task_type: str,
        model_used: str,
        prompt: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        latency_ms: int = 0,
        decision_summary: str = "",
        alternatives_considered: list[str] | None = None,
        confidence_in_decision: float = 0.0,
    ) -> dict[str, Any]:
        """Build a trace dict from a call; the prompt is hashed, not stored."""
        return {
            "llm_decision_id": str(UlidFactory()),
            "request_id": request_id,
            "step_id": step_id,
            "task_type": task_type,
            "model_used": model_used,
            "prompt_hash": hash_prompt(prompt),
            "input_token_count": input_tokens,
            "output_token_count": output_tokens,
            "latency_ms": latency_ms,
            "decision_summary": decision_summary,
            "alternatives_considered": list(alternatives_considered or []),
            "confidence_in_decision": confidence_in_decision,
            "timestamp": datetime.now(UTC),
        }

    def write(self, trace: Mapping[str, Any]) -> dict[str, Any]:
        """Validate, complete and store a trace in memory.

        Args:
            trace: Mapping with at least the ``REQUIRED_FIELDS`` keys.

        Returns:
            The stored trace dict (with generated id/timestamp when missing).

        Raises:
            ValidationError: On missing fields, bad task type or bad score.
        """
        missing = sorted(REQUIRED_FIELDS - set(trace.keys()))
        if missing:
            raise ValidationError(f"llm_decision_trace missing fields: {missing}")
        task_type = trace["task_type"]
        if task_type not in TASK_TYPES:
            raise ValidationError(f"Invalid task_type for llm_decision_trace: {task_type}")
        confidence = trace.get("confidence_in_decision", 0.0)
        if not isinstance(confidence, (int, float)) or not 0.0 <= float(confidence) <= 1.0:
            raise ValidationError("confidence_in_decision must be a float in 0-1")
        stored: dict[str, Any] = dict(trace)
        stored.setdefault("llm_decision_id", str(UlidFactory()))
        stored.setdefault("timestamp", datetime.now(UTC))
        stored.setdefault("input_token_count", 0)
        stored.setdefault("output_token_count", 0)
        stored.setdefault("latency_ms", 0)
        stored.setdefault("decision_summary", "")
        stored.setdefault("alternatives_considered", [])
        stored.setdefault("confidence_in_decision", 0.0)
        self._traces.append(stored)
        if self._engine is not None:
            self._insert_rows(self._engine, [stored])
        return stored

    def list_traces(self) -> list[dict[str, Any]]:
        """Return stored traces (copies, oldest first)."""
        return [dict(trace) for trace in self._traces]

    def clear(self) -> None:
        """Drop all in-memory traces."""
        self._traces.clear()

    def persist(self, engine: Any | None = None) -> int:
        """INSERT all in-memory traces into ``llm_decision_trace``.

        Args:
            engine: SQLAlchemy sync engine (defaults to the bound engine).

        Returns:
            Number of rows inserted.

        Raises:
            ValidationError: If no engine is available.
        """
        target = engine or self._engine
        if target is None:
            raise ValidationError("LLMTraceWriter.persist requires an engine")
        return self._insert_rows(target, self._traces)

    @staticmethod
    def _insert_rows(engine: Any, traces: list[dict[str, Any]]) -> int:
        """Insert trace dicts; return the inserted row count."""
        _METADATA.create_all(engine, tables=[LLM_DECISION_TRACE_TABLE], checkfirst=True)
        if not traces:
            return 0
        rows = [
            {
                "llm_decision_id": trace["llm_decision_id"],
                "request_id": trace["request_id"],
                "step_id": trace["step_id"],
                "task_type": trace["task_type"],
                "model_used": trace["model_used"],
                "prompt_hash": trace["prompt_hash"],
                "input_token_count": int(trace.get("input_token_count", 0)),
                "output_token_count": int(trace.get("output_token_count", 0)),
                "latency_ms": int(trace.get("latency_ms", 0)),
                "decision_summary": str(trace.get("decision_summary", "")),
                "alternatives_considered": json.dumps(
                    trace.get("alternatives_considered", [])
                ),
                "confidence_in_decision": float(trace.get("confidence_in_decision", 0.0)),
                "timestamp": trace.get("timestamp") or datetime.now(UTC),
            }
            for trace in traces
        ]
        with engine.begin() as connection:
            connection.execute(LLM_DECISION_TRACE_TABLE.insert(), rows)
        return len(rows)
