"""In-memory and database-backed lineage graphs for INIS transformations.

Persistence is asynchronous and observable: :meth:`LineageTracker.record`
schedules a write when an event loop is running, :meth:`LineageTracker.flush`
awaits the pending writes (including records queued outside a loop), and every
failure is captured in :attr:`LineageTracker.persistence_errors` instead of
being silently lost.
"""

import asyncio
import json
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.errors import InfrastructureError


class LineageTracker:
    """Record resource transformations and retrieve transitive lineage."""

    def __init__(self, engine: AsyncEngine | None = None) -> None:
        self._engine = engine
        self._transformations: dict[str, dict[str, tuple[str, ...]]] = {}
        self._parents: dict[str, set[str]] = {}
        self._children: dict[str, set[str]] = {}
        self._pending_records: list[dict] = []
        self._persistence_tasks: list[asyncio.Task[None]] = []
        self._persistence_errors: list[str] = []

    @property
    def persistence_enabled(self) -> bool:
        """Whether transformations are written to a database engine."""
        return self._engine is not None

    @property
    def persistence_errors(self) -> list[str]:
        """Failures captured from background or flushed persistence attempts."""
        return list(self._persistence_errors)

    @property
    def pending_records(self) -> int:
        """Records queued outside a running event loop, awaiting :meth:`flush`."""
        return len(self._pending_records)

    def record(
        self,
        transformation_id: str,
        input_ids: list[str],
        output_ids: list[str],
    ) -> None:
        """Record links from each input resource to each output resource."""
        self._transformations[transformation_id] = {
            "input_ids": tuple(input_ids),
            "output_ids": tuple(output_ids),
        }
        for input_id in input_ids:
            self._children.setdefault(input_id, set()).update(output_ids)
        for output_id in output_ids:
            self._parents.setdefault(output_id, set()).update(input_ids)

        if self._engine is not None:
            record = self._persistence_record(transformation_id, input_ids, output_ids)
            try:
                task = asyncio.get_running_loop().create_task(
                    self._persist_record(self._engine, record)
                )
            except RuntimeError:
                # No running loop: the record waits for flush() instead of being
                # dropped on the floor.
                self._pending_records.append(record)
            else:
                task.add_done_callback(self._on_persistence_done)
                self._persistence_tasks.append(task)

    def _on_persistence_done(self, task: asyncio.Task[None]) -> None:
        """Capture background failures so they are never silently lost."""
        if task.cancelled():
            self._persistence_errors.append("lineage persistence task cancelled")
            return
        error = task.exception()
        if error is not None:
            self._persistence_errors.append(f"{type(error).__name__}: {error}")

    async def flush(self) -> int:
        """Persist every queued transformation; return how many were written.

        Errors are collected in :attr:`persistence_errors`, so ``flush`` never
        raises and stays safe on shutdown paths.
        """
        persisted = 0
        while self._persistence_tasks:
            task = self._persistence_tasks.pop(0)
            result = await asyncio.gather(task, return_exceptions=True)
            if not isinstance(result[0], BaseException):
                persisted += 1

        if self._engine is None:
            return persisted

        queued, self._pending_records = self._pending_records, []
        for record in queued:
            try:
                await self._persist_record(self._engine, record)
            except Exception as exc:  # noqa: BLE001 - collected in persistence_errors
                self._persistence_errors.append(f"{type(exc).__name__}: {exc}")
                continue
            persisted += 1
        return persisted

    async def aclose(self) -> None:
        """Flush pending writes; convenience alias for shutdown paths."""
        await self.flush()

    def get_lineage(self, resource_id: str) -> dict[str, list[str]]:
        """Return all upstream ancestry and downstream descendants of a resource."""
        return {
            "ancestry": sorted(self._reachable(resource_id, self._parents)),
            "descendants": sorted(self._reachable(resource_id, self._children)),
        }

    @classmethod
    async def load_from_db(cls, engine: AsyncEngine, resource_id: str) -> dict[str, list[str]]:
        """Build resource lineage from transformations stored in the database.

        ``input_ids``/``output_ids`` are JSONB columns; a raw SQL read returns
        them either as decoded sequences or as JSON text, so both shapes are
        accepted.
        """
        async with engine.connect() as connection:
            result = await connection.execute(
                text("SELECT transformation_id, input_ids, output_ids FROM transformations")
            )

        tracker = cls()
        for row in result.mappings().all():
            transformation = dict(row)
            tracker.record(
                transformation["transformation_id"],
                cls._as_id_list(transformation["input_ids"]),
                cls._as_id_list(transformation["output_ids"]),
            )
        return tracker.get_lineage(resource_id)

    @staticmethod
    def _as_id_list(value: object) -> list[str]:
        """Decode a JSONB identifier list (JSON text, sequence or ``None``)."""
        if value is None:
            return []
        if isinstance(value, str):
            value = json.loads(value)
        if isinstance(value, (list, tuple, set)):
            return [str(item) for item in value]
        raise InfrastructureError(
            f"unsupported identifier column payload: {type(value).__name__}"
        )

    @staticmethod
    def _persistence_record(
        transformation_id: str, input_ids: list[str], output_ids: list[str]
    ) -> dict:
        """Create the complete persistence representation from the public record API.

        JSONB values are bound as JSON text and cast server-side by
        :meth:`_persist_record`; the timestamp stays a ``datetime`` object so the
        driver writes a real ``timestamptz`` instead of parsing a string.
        """
        return {
            "transformation_id": transformation_id,
            "input_ids": json.dumps(list(input_ids)),
            "output_ids": json.dumps(list(output_ids)),
            "operator": None,
            "tool": None,
            "tool_version": None,
            "parameters": json.dumps({}),
            "timestamp": datetime.now(UTC),
            "result": None,
            "justification": None,
        }

    @staticmethod
    async def _persist_record(engine: AsyncEngine, record: dict) -> None:
        """Insert one transformation through the configured asynchronous engine."""
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO transformations (
                        transformation_id, input_ids, output_ids, operator, tool,
                        tool_version, parameters, timestamp, result, justification
                    ) VALUES (
                        :transformation_id, CAST(:input_ids AS JSONB), CAST(:output_ids AS JSONB),
                        :operator, :tool, :tool_version, CAST(:parameters AS JSONB),
                        :timestamp, :result, :justification
                    )
                    """
                ),
                record,
            )

    @staticmethod
    def _reachable(resource_id: str, links: dict[str, set[str]]) -> set[str]:
        """Traverse graph links without looping when transformations form a cycle."""
        discovered: set[str] = set()
        pending = list(links.get(resource_id, set()))
        while pending:
            candidate = pending.pop()
            if candidate in discovered or candidate == resource_id:
                continue
            discovered.add(candidate)
            pending.extend(links.get(candidate, set()))
        return discovered
