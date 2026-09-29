"""§16.2/§41.13 — vector and hybrid search latency on a real pgvector corpus.

§41.13 asks for a sizing answer on the retrieval path, which is the only
component whose cost depends on the data volume rather than on the request. The
test seeds the shared corpus, then times exact-match, unrelated and hybrid
queries, and asserts that the answers are correct as well as fast — a fast search
that returns nothing would otherwise pass a latency-only check.

Runs against the pgvector container (skip when Docker is unavailable).
"""

from __future__ import annotations

import statistics
import time

import pytest

from app.storage.search.hybrid_search import HybridSearch
from app.storage.search.vector_search import VectorSearch
from tests.integration.search_corpus import seed_corpus

pytestmark = pytest.mark.asyncio

#: Queries timed per measurement.
QUERIES = 12

#: Upper bound on the median latency of a single search (seconds).
MAX_MEDIAN_LATENCY = 0.25

#: Upper bound on the p95 latency (seconds) — sized for the HNSW index.
MAX_P95_LATENCY = 1.0

#: Lexical query matching exactly one unit of the seeded corpus.
LEXICAL_QUERY = "Paris capital of France"


def _vector(raw: str) -> list[float]:
    """Parse the corpus' PostgreSQL vector literal into floats."""
    return [float(part) for part in raw.strip("[]").split(",")]


async def _timed(callable_, times: int = QUERIES) -> list[float]:
    """Return the durations (seconds) of *times* awaited calls."""
    durations: list[float] = []
    for _ in range(times):
        started = time.perf_counter()
        await callable_()
        durations.append(time.perf_counter() - started)
    return durations


@pytest.fixture
async def corpus(db_url: str) -> dict[str, str]:
    """Seed the shared corpus used by both searches."""
    return await seed_corpus(db_url)


class TestVectorSearchLatency:
    """§16.1/§41.13 — exact and unrelated queries stay fast and correct."""

    async def test_identical_query_returns_the_seeded_unit(
        self, db_url: str, corpus: dict[str, str]
    ) -> None:
        """The timed query is meaningful: it really finds its own unit."""
        results = await VectorSearch(db_url).search(
            owner_type="information_unit",
            query_vector=_vector(corpus["semantic_vector"]),
            limit=10,
        )

        assert results, "the corpus is not searchable: the timing would be meaningless"
        assert results[0][0] == corpus["semantic_unit"]

    async def test_median_and_tail_latency_are_bounded(
        self, db_url: str, corpus: dict[str, str]
    ) -> None:
        """Median and p95 latency of a vector search stay within budget."""
        search = VectorSearch(db_url)
        vector = _vector(corpus["semantic_vector"])

        durations = await _timed(
            lambda: search.search(owner_type="information_unit", query_vector=vector, limit=10)
        )
        durations.sort()
        median = statistics.median(durations)
        p95 = durations[min(len(durations) - 1, int(len(durations) * 0.95))]

        assert median < MAX_MEDIAN_LATENCY, f"median vector search {median:.3f}s is too slow"
        assert p95 < MAX_P95_LATENCY, f"p95 vector search {p95:.3f}s is too slow"


class TestHybridSearchLatency:
    """§16.2/§41.13 — the combined search keeps both halves reachable."""

    async def test_hybrid_search_finds_the_lexical_unit(
        self, db_url: str, corpus: dict[str, str]
    ) -> None:
        """The lexical half of the hybrid search is actually populated (§16.2)."""
        results = await HybridSearch(db_url).search(
            query=LEXICAL_QUERY, query_vector=_vector(corpus["semantic_vector"]), limit=10
        )

        assert results, "the hybrid search returned nothing"
        assert corpus["lexical_unit"] in {row["owner_id"] for row in results}

    async def test_hybrid_search_latency_is_bounded(
        self, db_url: str, corpus: dict[str, str]
    ) -> None:
        """The hybrid search stays within the same latency budget."""
        search = HybridSearch(db_url)
        vector = _vector(corpus["semantic_vector"])

        durations = await _timed(
            lambda: search.search(query=LEXICAL_QUERY, query_vector=vector, limit=10)
        )
        durations.sort()

        assert statistics.median(durations) < MAX_P95_LATENCY

