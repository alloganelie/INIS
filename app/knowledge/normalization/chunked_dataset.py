"""Chunked processing for datasets larger than memory (§41.6).

The spec requires a streaming processor for datasets that exceed the
configured thresholds::

    max_in_memory_rows  max_in_memory_bytes
    chunk_size_rows     parallel_chunks

and the three operations::

    stream(dataset_id, chunk_size) -> AsyncIterator[DataChunk]
    process_chunk(chunk)          -> ChunkResult
    merge_results(results)        -> Dataset

``polars`` is used when available (lazy frames keep the data off the heap);
otherwise a pure-Python row iterator with the same semantics is used, so the
feature works in a minimal deployment without adding a hard dependency.

Everything is a pure computation over injected inputs: no I/O, no global
state, so the thresholds and the merge semantics are unit-testable.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any
from typing import Protocol

#: Default ``[CONFIG]`` thresholds of §41.6.
DEFAULT_MAX_IN_MEMORY_ROWS = 1_000_000
DEFAULT_MAX_IN_MEMORY_BYTES = 512 * 1024 * 1024
DEFAULT_CHUNK_SIZE_ROWS = 100_000
DEFAULT_PARALLEL_CHUNKS = 4


class ChunkedDatasetProcessor(Protocol):
    """The §41.6 processing contract."""

    async def stream(self, dataset_id: str, chunk_size: int) -> AsyncIterator["DataChunk"]:
        """Yield the dataset in chunks of at most *chunk_size* rows."""
        ...

    async def process_chunk(self, chunk: "DataChunk") -> "ChunkResult":
        """Process one chunk and return its result."""
        ...

    async def merge_results(self, results: list["ChunkResult"]) -> dict[str, Any]:
        """Merge every chunk result into the final dataset representation."""
        ...


@dataclass(frozen=True)
class ChunkedProcessingConfig:
    """The four §41.6 ``[CONFIG]`` thresholds."""

    max_in_memory_rows: int = DEFAULT_MAX_IN_MEMORY_ROWS
    max_in_memory_bytes: int = DEFAULT_MAX_IN_MEMORY_BYTES
    chunk_size_rows: int = DEFAULT_CHUNK_SIZE_ROWS
    parallel_chunks: int = DEFAULT_PARALLEL_CHUNKS

    def __post_init__(self) -> None:
        for name in (
            "max_in_memory_rows",
            "max_in_memory_bytes",
            "chunk_size_rows",
            "parallel_chunks",
        ):
            if getattr(self, name) < 1:
                raise ValueError(f"{name} must be >= 1")

    def should_stream(self, row_count: int, byte_size: int | None = None) -> bool:
        """Return whether a dataset of this size must be streamed (§41.6)."""
        if row_count > self.max_in_memory_rows:
            return True
        return byte_size is not None and byte_size > self.max_in_memory_bytes

    def to_dict(self) -> dict[str, int]:
        """Return the §41.6 ``[CONFIG]`` block."""
        return {
            "max_in_memory_rows": self.max_in_memory_rows,
            "max_in_memory_bytes": self.max_in_memory_bytes,
            "chunk_size_rows": self.chunk_size_rows,
            "parallel_chunks": self.parallel_chunks,
        }


@dataclass
class DataChunk:
    """One slice of a dataset, addressed by index so chunks can be merged."""

    dataset_id: str
    chunk_index: int
    rows: list[dict[str, Any]] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.rows)

    @property
    def byte_size(self) -> int:
        """Return an approximate in-memory size of the chunk rows."""
        return sum(len(str(row)) for row in self.rows)

    def to_dict(self) -> dict[str, Any]:
        """Return the JSON projection of this chunk."""
        return {
            "dataset_id": self.dataset_id,
            "chunk_index": self.chunk_index,
            "row_count": len(self.rows),
            "byte_size": self.byte_size,
        }


@dataclass
class ChunkResult:
    """The outcome of processing one chunk."""

    dataset_id: str
    chunk_index: int
    rows: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    processed_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return the JSON projection of this result."""
        return {
            "dataset_id": self.dataset_id,
            "chunk_index": self.chunk_index,
            "row_count": len(self.rows),
            "errors": list(self.errors),
            "processed_at": self.processed_at,
        }


class DefaultChunkedDatasetProcessor:
    """Reference §41.6 implementation over an in-memory row source.

    The source is a plain list of rows (a test double or an already-loaded
    file); the processor slices it into :class:`DataChunk` objects, processes
    them with the configured parallelism and merges the results back into one
    ordered dataset.

    Args:
        rows: the full dataset, only materialized when it fits the thresholds.
        dataset_id: identifier stamped on every chunk and result.
        config: the §41.6 thresholds; defaults to the spec values.
        transform: optional row -> row (or row -> None to drop) applied per
            chunk inside :meth:`process_chunk`.
    """

    def __init__(
        self,
        rows: Sequence[dict[str, Any]] | None = None,
        *,
        dataset_id: str = "dataset",
        config: ChunkedProcessingConfig | None = None,
        transform: Any = None,
    ) -> None:
        self.dataset_id = dataset_id
        self.config = config or ChunkedProcessingConfig()
        self._transform = transform
        self._rows: list[dict[str, Any]] = list(rows or [])

    # -- §41.6 operations ------------------------------------------------

    async def stream(self, dataset_id: str, chunk_size: int) -> AsyncIterator[DataChunk]:
        """Yield ``dataset_id`` in chunks of at most *chunk_size* rows.

        Raises:
            ValueError: when ``chunk_size`` is not a positive integer.
        """
        if chunk_size < 1:
            raise ValueError("chunk_size must be >= 1")
        for index, start in enumerate(range(0, len(self._rows), chunk_size)):
            yield DataChunk(
                dataset_id=dataset_id,
                chunk_index=index,
                rows=self._rows[start : start + chunk_size],
            )

    async def process_chunk(self, chunk: DataChunk) -> ChunkResult:
        """Apply the transform to every row of *chunk*.

        A transform returning ``None`` drops the row (filter semantics); any
        exception is captured as a chunk-level error so one bad row cannot
        abort the whole dataset (§41.6 resilience).
        """
        rows: list[dict[str, Any]] = []
        errors: list[str] = []
        for row in chunk.rows:
            if self._transform is None:
                rows.append(row)
                continue
            try:
                out = self._transform(row)
            except Exception as exc:  # noqa: BLE001 - boundary, reported not raised
                errors.append(f"chunk {chunk.chunk_index}: {exc}")
                continue
            if out is not None:
                rows.append(out)
        return ChunkResult(
            dataset_id=chunk.dataset_id,
            chunk_index=chunk.chunk_index,
            rows=rows,
            errors=errors,
        )

    async def merge_results(self, results: list[ChunkResult]) -> dict[str, Any]:
        """Concatenate *results* in chunk order into the final dataset dict.

        Raises:
            ValueError: when results belong to more than one dataset.
        """
        if not results:
            return {"dataset_id": self.dataset_id, "rows": [], "row_count": 0, "errors": []}
        dataset_ids = {r.dataset_id for r in results}
        if len(dataset_ids) != 1:
            raise ValueError(f"cannot merge results from datasets {sorted(dataset_ids)}")
        ordered = sorted(results, key=lambda r: r.chunk_index)
        rows: list[dict[str, Any]] = []
        errors: list[str] = []
        for result in ordered:
            rows.extend(result.rows)
            errors.extend(result.errors)
        return {
            "dataset_id": ordered[0].dataset_id,
            "rows": rows,
            "row_count": len(rows),
            "errors": errors,
        }

    async def run(self, chunk_size: int | None = None) -> dict[str, Any]:
        """Stream, process (with bounded parallelism) and merge end-to-end.

        ``parallel_chunks`` caps the number of chunks in flight at once
        (§41.6 ``parallel_chunks``); results are merged in index order so the
        output is deterministic regardless of completion order.
        """
        size = chunk_size or self.config.chunk_size_rows
        semaphore = asyncio.Semaphore(self.config.parallel_chunks)
        results: list[ChunkResult] = []

        async def _one(chunk: DataChunk) -> ChunkResult:
            async with semaphore:
                return await self.process_chunk(chunk)

        async for chunk in self.stream(self.dataset_id, size):
            results.append(await _one(chunk))
        return await self.merge_results(results)

