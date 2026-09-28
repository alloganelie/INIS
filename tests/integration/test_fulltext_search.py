"""Integration tests for §16.1 full-text search on real PostgreSQL tsvector.

The migrated schema carries ``information_units.search_vector`` (migration
0003) with a GIN index; this module proves the lexical half of the search
contract works against real rows, not a stub.
"""

from __future__ import annotations

import pytest

from app.storage.search.fulltext_search import FullTextSearch
from tests.integration.search_corpus import seed_corpus

#: Words present in exactly one seeded unit.
MATCHING_QUERY = "capital France"
MISSING_QUERY = "quantum chromodynamics"


@pytest.fixture
async def corpus(db_url: str) -> dict[str, str]:
    """Seed the shared search corpus."""
    return await seed_corpus(db_url)


class TestLexicalMatch:
    """§16.1 — tsvector matching returns the units that contain the terms."""

    async def test_matching_query_returns_the_unit(
        self, db_url: str, corpus: dict[str, str]
    ) -> None:
        """The unit whose text contains both terms is returned with a rank."""
        results = await FullTextSearch(db_url).search(MATCHING_QUERY, limit=10)
        owner_ids = [row["owner_id"] for row in results]
        assert corpus["lexical_unit"] in owner_ids
        scores = {row["owner_id"]: row["score"] for row in results}
        assert scores[corpus["lexical_unit"]] > 0

    async def test_unrelated_units_are_excluded(
        self, db_url: str, corpus: dict[str, str]
    ) -> None:
        """The other seeded units do not match the query."""
        results = await FullTextSearch(db_url).search(MATCHING_QUERY, limit=10)
        owner_ids = {row["owner_id"] for row in results}
        assert corpus["semantic_unit"] not in owner_ids
        assert corpus["isolated_unit"] not in owner_ids

    async def test_no_match_returns_empty(self, db_url: str, corpus: dict[str, str]) -> None:
        """A query with no lexeme in the corpus yields no row."""
        results = await FullTextSearch(db_url).search(MISSING_QUERY, limit=10)
        assert results == []

    async def test_result_shape(self, db_url: str, corpus: dict[str, str]) -> None:
        """Each row exposes ``owner_id`` and a float ``score``."""
        results = await FullTextSearch(db_url).search(MATCHING_QUERY, limit=10)
        assert results
        for row in results:
            assert set(row) == {"owner_id", "score"}
            assert isinstance(row["score"], float)

    async def test_limit_is_honoured(self, db_url: str, corpus: dict[str, str]) -> None:
        """``limit`` bounds the number of returned rows."""
        results = await FullTextSearch(db_url).search(MATCHING_QUERY, limit=1)
        assert len(results) <= 1

    async def test_ranking_is_descending(
        self, db_url: str, corpus: dict[str, str]
    ) -> None:
        """Results are ordered by descending ``ts_rank``."""
        results = await FullTextSearch(db_url).search(MATCHING_QUERY, limit=10)
        scores = [row["score"] for row in results]
        assert scores == sorted(scores, reverse=True)


class TestDegradedMode:
    """§9.1 — no usable driver means an empty result, never an exception."""

    async def test_unusable_driver_returns_empty(self) -> None:
        """An unusable connection string yields an empty list."""
        assert await FullTextSearch("nosuchdriver://localhost/db").search("anything") == []

