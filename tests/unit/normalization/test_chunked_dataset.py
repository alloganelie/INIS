"""Unit tests for the §41.6 chunked dataset processor."""

import pytest

from app.knowledge.normalization.chunked_dataset import (
    DEFAULT_CHUNK_SIZE_ROWS,
    DEFAULT_MAX_IN_MEMORY_BYTES,
    DEFAULT_MAX_IN_MEMORY_ROWS,
    DEFAULT_PARALLEL_CHUNKS,
    ChunkResult,
    ChunkedProcessingConfig,
    DataChunk,
    DefaultChunkedDatasetProcessor,
)

ROWS = [{"i": i, "v": i * 10} for i in range(10)]


def test_config_defaults_match_the_spec() -> None:
    config = ChunkedProcessingConfig()
    assert config.max_in_memory_rows == DEFAULT_MAX_IN_MEMORY_ROWS
    assert config.max_in_memory_bytes == DEFAULT_MAX_IN_MEMORY_BYTES
    assert config.chunk_size_rows == DEFAULT_CHUNK_SIZE_ROWS
    assert config.parallel_chunks == DEFAULT_PARALLEL_CHUNKS


def test_config_rejects_non_positive_values() -> None:
    with pytest.raises(ValueError, match="chunk_size_rows"):
        ChunkedProcessingConfig(chunk_size_rows=0)
    with pytest.raises(ValueError, match="parallel_chunks"):
        ChunkedProcessingConfig(parallel_chunks=0)


def test_should_stream_on_row_and_byte_thresholds() -> None:
    config = ChunkedProcessingConfig(max_in_memory_rows=10, max_in_memory_bytes=100)
    assert config.should_stream(11) is True
    assert config.should_stream(10) is False
    assert config.should_stream(1, 101) is True
    assert config.should_stream(1, 100) is False


def test_config_to_dict_block() -> None:
    assert set(ChunkedProcessingConfig().to_dict()) == {
        "max_in_memory_rows",
        "max_in_memory_bytes",
        "chunk_size_rows",
        "parallel_chunks",
    }


@pytest.mark.asyncio
async def test_stream_slices_into_bounded_chunks() -> None:
    processor = DefaultChunkedDatasetProcessor(ROWS, dataset_id="ds1")
    chunks = [c async for c in processor.stream("ds1", 4)]
    assert [len(c) for c in chunks] == [4, 4, 2]
    assert [c.chunk_index for c in chunks] == [0, 1, 2]
    assert all(c.dataset_id == "ds1" for c in chunks)


@pytest.mark.asyncio
async def test_stream_rejects_invalid_chunk_size() -> None:
    processor = DefaultChunkedDatasetProcessor(ROWS)
    with pytest.raises(ValueError, match="chunk_size"):
        async for _ in processor.stream("ds1", 0):  # pragma: no cover
            pass


@pytest.mark.asyncio
async def test_process_chunk_identity_without_transform() -> None:
    processor = DefaultChunkedDatasetProcessor(ROWS)
    result = await processor.process_chunk(DataChunk("ds1", 0, ROWS[:3]))
    assert result.rows == ROWS[:3]
    assert result.errors == []


@pytest.mark.asyncio
async def test_process_chunk_filters_and_reports_errors() -> None:
    def transform(row: dict) -> dict | None:
        if row["i"] == 1:
            raise RuntimeError("bad row")
        if row["i"] == 2:
            return None  # drop
        return row

    processor = DefaultChunkedDatasetProcessor(ROWS, transform=transform)
    result = await processor.process_chunk(DataChunk("ds1", 0, ROWS[:3]))
    assert [r["i"] for r in result.rows] == [0]
    assert len(result.errors) == 1
    assert "bad row" in result.errors[0]


@pytest.mark.asyncio
async def test_merge_results_orders_chunks_and_collects_errors() -> None:
    processor = DefaultChunkedDatasetProcessor(ROWS, dataset_id="ds1")
    out_of_order = [
        ChunkResult("ds1", 2, rows=[{"i": 8}, {"i": 9}]),
        ChunkResult("ds1", 0, rows=[{"i": 0}], errors=["e0"]),
        ChunkResult("ds1", 1, rows=[{"i": 4}], errors=["e1"]),
    ]
    merged = await processor.merge_results(out_of_order)
    assert [r["i"] for r in merged["rows"]] == [0, 4, 8, 9]
    assert merged["row_count"] == 4
    assert merged["errors"] == ["e0", "e1"]
    assert merged["dataset_id"] == "ds1"


@pytest.mark.asyncio
async def test_merge_rejects_mixed_datasets() -> None:
    processor = DefaultChunkedDatasetProcessor(ROWS, dataset_id="ds1")
    with pytest.raises(ValueError, match="cannot merge"):
        await processor.merge_results(
            [ChunkResult("ds1", 0), ChunkResult("other", 1)]
        )


@pytest.mark.asyncio
async def test_merge_empty_results_is_an_empty_dataset() -> None:
    processor = DefaultChunkedDatasetProcessor([], dataset_id="ds1")
    merged = await processor.merge_results([])
    assert merged == {"dataset_id": "ds1", "rows": [], "row_count": 0, "errors": []}


@pytest.mark.asyncio
async def test_run_end_to_end_with_transform() -> None:
    processor = DefaultChunkedDatasetProcessor(
        ROWS,
        dataset_id="ds1",
        config=ChunkedProcessingConfig(chunk_size_rows=3, parallel_chunks=2),
        transform=lambda row: {**row, "v": row["v"] + 1} if row["i"] % 2 == 0 else row,
    )
    merged = await processor.run()
    assert merged["row_count"] == 10
    assert [r["i"] for r in merged["rows"]] == list(range(10))  # order preserved
    assert merged["rows"][0]["v"] == 1  # transformed
    assert merged["rows"][1]["v"] == 10  # untouched


def test_data_chunk_to_dict_and_byte_size() -> None:
    chunk = DataChunk("ds1", 3, ROWS[:2])
    payload = chunk.to_dict()
    assert payload["dataset_id"] == "ds1"
    assert payload["chunk_index"] == 3
    assert payload["row_count"] == 2
    assert payload["byte_size"] == chunk.byte_size > 0

