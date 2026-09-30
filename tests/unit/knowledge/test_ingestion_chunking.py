"""ADR 007/§41.6 — beyond the threshold, extraction really works by chunks.

``docs/adr/007_chunked_processing_threshold.md`` makes chunking mandatory beyond
``max_information_units_per_request`` (default 50). Until L2.6 that ceiling was a
document with no reader: the §41.6 processor existed but no real path reached it.
These tests hold the wiring in place:

* the threshold is resolved from the environment, with the ADR default;
* beyond it, ``DefaultChunkedDatasetProcessor`` streams the items in chunks of at
  most that size and merges them **in order**;
* below it, no processor is instantiated at all — the direct path stays direct;
* both paths produce the *same* units, which is what makes chunking a memory
  bound rather than a behaviour change;
* an item that cannot become a unit is named in ``limitations``, never dropped in
  silence (§25.2).
"""

from __future__ import annotations

from typing import ClassVar

import pytest

from app.knowledge.ingestion import document_ingestor
from app.knowledge.ingestion.document_ingestor import ingest_document
from app.knowledge.normalization.chunked_dataset import DefaultChunkedDatasetProcessor
from app.knowledge.normalization.limits import (
    DEFAULT_MAX_INFORMATION_UNITS_PER_REQUEST,
    MAX_INFORMATION_UNITS_PER_REQUEST_ENV,
    chunked_processing_config,
    max_information_units_per_request,
)
from tests.factories import pdf_bytes

DOCUMENT_ID = "DOC_01M3Q0000000000000000000AA"
SOURCE_ID = "SRC_01M3Q0000000000000000000AA"
REQUEST_ID = "REQ_01M3Q0000000000000000000AA"
STORAGE_REF = "s3://inis-artifacts/documents/REQ_1/chunk.csv"


def _csv(rows: int) -> bytes:
    """Return a CSV with *rows* data rows."""
    lines = ["city,population"]
    lines += [f"ville{i},{i * 1000}" for i in range(1, rows + 1)]
    return ("\n".join(lines) + "\n").encode("utf-8")


async def _ingest_csv(rows: int):
    return await ingest_document(
        document_id=DOCUMENT_ID,
        source_id=SOURCE_ID,
        request_id=REQUEST_ID,
        file_name="chunk.csv",
        mime_type="text/csv",
        data=_csv(rows),
        storage_ref=STORAGE_REF,
    )


class TestThresholdResolution:
    """The ADR ceiling is a real setting, not a comment."""

    def test_the_default_is_the_adr_one(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(MAX_INFORMATION_UNITS_PER_REQUEST_ENV, raising=False)

        assert max_information_units_per_request() == 50
        assert max_information_units_per_request() == (
            DEFAULT_MAX_INFORMATION_UNITS_PER_REQUEST
        )

    def test_the_environment_overrides_the_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(MAX_INFORMATION_UNITS_PER_REQUEST_ENV, "7")

        assert max_information_units_per_request() == 7

    @pytest.mark.parametrize("value", ["", "zéro", "0", "-3"])
    def test_an_unusable_value_falls_back_to_the_default(
        self, monkeypatch: pytest.MonkeyPatch, value: str
    ) -> None:
        """A threshold nobody can state is a threshold nobody enforces."""
        monkeypatch.setenv(MAX_INFORMATION_UNITS_PER_REQUEST_ENV, value)

        assert max_information_units_per_request() == (
            DEFAULT_MAX_INFORMATION_UNITS_PER_REQUEST
        )

    def test_the_config_streams_exactly_beyond_the_threshold(self) -> None:
        config = chunked_processing_config(10)

        assert config.should_stream(10) is False
        assert config.should_stream(11) is True
        assert config.chunk_size_rows == 10
        assert config.max_in_memory_rows == 10

    def test_a_non_positive_threshold_is_refused(self) -> None:
        with pytest.raises(ValueError):
            chunked_processing_config(0)


class RecordingProcessor(DefaultChunkedDatasetProcessor):
    """A §41.6 processor that remembers how large the chunks it was given were."""

    instances: ClassVar[list[RecordingProcessor]] = []

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.chunk_sizes: list[int] = []
        RecordingProcessor.instances.append(self)

    async def process_chunk(self, chunk):  # type: ignore[no-untyped-def]
        self.chunk_sizes.append(len(chunk.rows))
        return await super().process_chunk(chunk)


@pytest.fixture
def recording_processor(monkeypatch: pytest.MonkeyPatch) -> type[RecordingProcessor]:
    """Replace the processor used by the ingestion, recording every chunk."""
    RecordingProcessor.instances = []
    monkeypatch.setattr(
        document_ingestor, "DefaultChunkedDatasetProcessor", RecordingProcessor
    )
    return RecordingProcessor


class TestChunkedPathIsUsed:
    """§41.6 — beyond the threshold, the processor is really in the path."""

    async def test_a_payload_beyond_the_threshold_is_chunked(
        self, monkeypatch: pytest.MonkeyPatch, recording_processor
    ) -> None:
        monkeypatch.setenv(MAX_INFORMATION_UNITS_PER_REQUEST_ENV, "50")

        outcome = await _ingest_csv(120)

        assert len(outcome.units) == 120
        assert len(recording_processor.instances) == 1
        sizes = recording_processor.instances[0].chunk_sizes
        assert sizes == [50, 50, 20]
        # §41.6 — no chunk ever exceeds the configured size.
        assert max(sizes) <= 50

    async def test_a_payload_below_the_threshold_keeps_the_direct_path(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No chunking, no processor: the small case must not pay for §41.6."""
        monkeypatch.setenv(MAX_INFORMATION_UNITS_PER_REQUEST_ENV, "50")

        def _forbidden(*args: object, **kwargs: object):
            raise AssertionError("the processor must not run below the threshold")

        monkeypatch.setattr(
            document_ingestor, "DefaultChunkedDatasetProcessor", _forbidden
        )

        outcome = await _ingest_csv(3)

        assert len(outcome.units) == 3

    async def test_prose_is_chunked_too(self, monkeypatch: pytest.MonkeyPatch,
                                        recording_processor) -> None:
        """A 60-page PDF exceeds the threshold as surely as a 60-row CSV."""
        monkeypatch.setenv(MAX_INFORMATION_UNITS_PER_REQUEST_ENV, "50")
        pages = [f"Page {index} raconte une histoire assez longue." for index in range(1, 61)]

        outcome = await ingest_document(
            document_id=DOCUMENT_ID,
            source_id=SOURCE_ID,
            request_id=REQUEST_ID,
            file_name="rapport.pdf",
            mime_type="application/pdf",
            data=pdf_bytes(pages),
            storage_ref=STORAGE_REF + ".pdf",
        )

        assert len(outcome.units) == 60
        assert recording_processor.instances[0].chunk_sizes == [50, 10]
        assert [unit["location"]["page"] for unit in outcome.units] == list(range(1, 61))



class TestChunkingIsTransparent:
    """Chunking bounds memory; it must not change a single unit."""

    async def test_the_units_are_the_same_chunked_or_not(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def shape(outcome):
            """Return the observable shape of an outcome, ignoring minted ids."""
            return [
                (
                    unit["location"]["row"],
                    unit["content"]["values"],
                    unit["provenance"]["method"],
                    unit["data_stage"],
                )
                for unit in outcome.units
            ]

        monkeypatch.setenv(MAX_INFORMATION_UNITS_PER_REQUEST_ENV, "10")
        chunked = await _ingest_csv(35)

        monkeypatch.setenv(MAX_INFORMATION_UNITS_PER_REQUEST_ENV, "100000")
        direct = await _ingest_csv(35)

        assert shape(chunked) == shape(direct)
        assert chunked.dataset["row_count"] == direct.dataset["row_count"] == 35
        assert chunked.dataset["dataset_schema"] == direct.dataset["dataset_schema"]

    async def test_an_item_that_cannot_become_a_unit_is_named(
        self, monkeypatch: pytest.MonkeyPatch, recording_processor
    ) -> None:
        """§25.2 — a broken row is reported, and the others are still delivered."""
        monkeypatch.setenv(MAX_INFORMATION_UNITS_PER_REQUEST_ENV, "2")
        original = document_ingestor._base_unit

        def _explode_on_row_three(*, content, **kwargs):  # type: ignore[no-untyped-def]
            if content.get("values", {}).get("city") == "ville3":
                raise ValueError("ligne illisible")
            return original(content=content, **kwargs)

        monkeypatch.setattr(document_ingestor, "_base_unit", _explode_on_row_three)

        outcome = await _ingest_csv(5)

        assert len(outcome.units) == 4
        assert any("non produite" in text for text in outcome.limitations)
        assert any("ligne illisible" in text for text in outcome.limitations)

