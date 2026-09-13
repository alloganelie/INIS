"""In-memory and database-backed lineage graphs for INIS transformations."""

import asyncio
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


class LineageTracker:
    """Record resource transformations and retrieve transitive lineage."""

    def __init__(self, engine: AsyncEngine | None = None) -> None:
        self._engine = engine
        self._transformations: dict[str, dict[str, tuple[str, ...]]] = {}
        self._parents: dict[str, set[str]] = {}
        self._children: dict[str, set[str]] = {}
        self._pending_records: list[dict] = []
        self._persistence_tasks: list[asyncio.Task[None]] = []

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
                self._pending_records.append(record)
            else:
                self._persistence_tasks.append(task)

    def get_lineage(self, resource_id: str) -> dict[str, list[str]]:
        """Return all upstream ancestry and downstream descendants of a resource."""
        return {
            "ancestry": sorted(self._reachable(resource_id, self._parents)),
            "descendants": sorted(self._reachable(resource_id, self._children)),
        }

    @classmethod
    async def load_from_db(cls, engine: AsyncEngine, resource_id: str) -> dict[str, list[str]]:
        """Build resource lineage from transformations stored in the database."""
        async with engine.connect() as connection:
            result = await connection.execute(
                text("SELECT transformation_id, input_ids, output_ids FROM transformations")
            )

        tracker = cls()
        for row in result.mappings().all():
            transformation = dict(row)
            tracker.record(
                transformation["transformation_id"],
                list(transformation["input_ids"]),
                list(transformation["output_ids"]),
            )
        return tracker.get_lineage(resource_id)

    @staticmethod
    def _persistence_record(
        transformation_id: str, input_ids: list[str], output_ids: list[str]
    ) -> dict:
        """Create the complete persistence representation from the public record API."""
        return {
            "transformation_id": transformation_id,
            "input_ids": input_ids,
            "output_ids": output_ids,
            "operator": None,
            "tool": None,
            "tool_version": None,
            "parameters": {},
            "timestamp": datetime.now(UTC).isoformat(timespec="microseconds").replace(
                "+00:00", "Z"
            ),
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
                        :transformation_id, :input_ids, :output_ids, :operator, :tool,
                        :tool_version, :parameters, :timestamp, :result, :justification
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
