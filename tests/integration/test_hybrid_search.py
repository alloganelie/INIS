"""Integration tests for §16.2 hybrid search (semantic + lexical).

The fused query joins the pgvector ``embeddings`` table with the
``information_units.search_vector`` index through a ``FULL OUTER JOIN``, so a
unit found by only one of the two retrievers must still be returned — that is
the property this module pins.
"""

from __future__ import annotations

import pytest

from app.storage.search.hybrid_search import HybridSearch
from tests.integration.search_corpus import as_float_list, seed_corpus

#: Lexical half of the hybrid query (matches the lexical unit only).
LEXICAL_QUERY = "capital France"


@pytest.fixture
async def corpus(db_url: str) -> dict[str, str]:
    """Seed the shared search corpus."""
    return await seed_corpus(db_url)


class TestFusion:
    """§16.2 — both retrievers contribute to the fused ranking."""

    async def test_semantic_only_hit_is_returned(
        self, db_url: str, corpus: dict[str, str]
    ) -> None:
        """A unit with a matching embedding but no matching text is returned."""
        results = await HybridSearch(db_url).search(
            query="quantum chromodynamics",
            query_vector=as_float_list(corpus["semantic_vector"]),
            limit=10,
        )
        owner_ids = [row["owner_id"] for row in results]
        assert corpus["semantic_unit"] in owner_ids

    async def test_lexical_only_hit_is_returned(
        self, db_url: str, corpus: dict[str, str]
    ) -> None:
        """A unit found lexically but far from the query vector is returned."""
        results = await HybridSearch(db_url).search(
            query=LEXICAL_QUERY,
            query_vector=as_float_list(corpus["semantic_vector"]),
            limit=10,
        )
        owner_ids = [row["owner_id"] for row in results]
        assert corpus["lexical_unit"] in owner_ids

    async def test_semantic_hit_outranks_lexical_only_hit(
        self, db_url: str, corpus: dict[str, str]
    ) -> None:
        """§16.2 weights (0.6 semantic / 0.4 lexical) order the fused result."""
        results = await HybridSearch(db_url).search(
            query=LEXICAL_QUERY,
            query_vector=as_float_list(corpus["semantic_vector"]),
            limit=10,
        )
        scores = {row["owner_id"]: row["final_score"] for row in results}
        assert scores[corpus["semantic_unit"]] > scores[corpus["lexical_unit"]]

    async def test_final_score_is_a_non_negative_float(
        self, db_url: str, corpus: dict[str, str]
    ) -> None:
        """The weighted sum is exposed as ``final_score``."""
        results = await HybridSearch(db_url).search(
            query=LEXICAL_QUERY,
            query_vector=as_float_list(corpus["semantic_vector"]),
            limit=10,
        )
        assert results
        for row in results:
            assert set(row) == {"owner_id", "final_score"}
            assert isinstance(row["final_score"], float)
            assert row["final_score"] >= 0.0

    async def test_results_are_ordered_by_final_score(
        self, db_url: str, corpus: dict[str, str]
    ) -> None:
        """The fused ranking is descending."""
        results = await HybridSearch(db_url).search(
            query=LEXICAL_QUERY,
            query_vector=as_float_list(corpus["semantic_vector"]),
            limit=10,
        )
        scores = [row["final_score"] for row in results]
        assert scores == sorted(scores, reverse=True)

    async def test_unit_without_embedding_is_not_semantically_matched(
        self, db_url: str, corpus: dict[str, str]
    ) -> None:
        """A unit with neither text match nor embedding does not appear."""
        results = await HybridSearch(db_url).search(
            query="quantum chromodynamics",
            query_vector=as_float_list(corpus["semantic_vector"]),
            limit=10,
        )
        owner_ids = {row["owner_id"] for row in results}
        assert corpus["isolated_unit"] not in owner_ids

    async def test_limit_bounds_the_fused_result(
        self, db_url: str, corpus: dict[str, str]
    ) -> None:
        """``limit`` applies to both retrievers and to the final select."""
        results = await HybridSearch(db_url).search(
            query=LEXICAL_QUERY,
            query_vector=as_float_list(corpus["semantic_vector"]),
            limit=1,
        )
        assert len(results) == 1


class TestDegradedMode:
    """§9.1 — no usable driver means an empty result, never an exception."""

    async def test_unusable_driver_returns_empty(self) -> None:
        """An unusable connection string yields an empty list."""
        results = await HybridSearch("nosuchdriver://localhost/db").search(
            query="anything", query_vector=[0.0] * 4
        )
        assert results == []

