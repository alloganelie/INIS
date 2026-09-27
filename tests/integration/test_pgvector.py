"""Integration tests for §16.1 vector search on real pgvector.

Runs against the pgvector container: real ``vector(1536)`` column, real HNSW
index, real cosine distance operator. The corpus is seeded by
:mod:`tests.integration.search_corpus`.
"""

from __future__ import annotations

import pytest

from app.storage.search.vector_search import VectorSearch
from tests.integration.search_corpus import seed_corpus


@pytest.fixture
async def corpus(db_url: str) -> dict[str, str]:
    """Seed the shared search corpus."""
    return await seed_corpus(db_url)


class TestSemanticOrdering:
    """§16.1 — results are ordered by descending cosine similarity."""

    async def test_identical_vector_ranks_first(
        self, db_url: str, corpus: dict[str, str]
    ) -> None:
        """The unit whose embedding equals the query scores ~1.0 and comes first."""
        results = await VectorSearch(db_url).search(
            owner_type="information_unit",
            query_vector=[
                float(part) for part in corpus["semantic_vector"].strip("[]").split(",")
            ],
            limit=10,
        )
        assert results, "the seeded corpus must be searchable"
        owner_ids = [owner_id for owner_id, _ in results]
        assert owner_ids[0] == corpus["semantic_unit"]
        assert results[0][1] == pytest.approx(1.0, abs=1e-3)

    async def test_orthogonal_vector_scores_lower(
        self, db_url: str, corpus: dict[str, str]
    ) -> None:
        """The orthogonal embedding ranks after the identical one."""
        search = VectorSearch(db_url)
        vector = [
            float(part) for part in corpus["semantic_vector"].strip("[]").split(",")
        ]
        results = await search.search(
            owner_type="information_unit", query_vector=vector, limit=10
        )
        scores = {owner_id: score for owner_id, score in results}
        assert scores[corpus["semantic_unit"]] > scores[corpus["lexical_unit"]]
        assert scores[corpus["lexical_unit"]] < 0.1

    async def test_scores_stay_in_the_similarity_range(
        self, db_url: str, corpus: dict[str, str]
    ) -> None:
        """Cosine similarity is bounded by [-1, 1]."""
        vector = [
            float(part) for part in corpus["semantic_vector"].strip("[]").split(",")
        ]
        results = await VectorSearch(db_url).search(
            owner_type="information_unit", query_vector=vector, limit=10
        )
        assert all(-1.0 <= score <= 1.0 for _, score in results)


class TestLimitsAndFilters:
    """§16.1 — ``limit`` and ``owner_type`` filter the candidate set."""

    async def test_limit_is_honoured(self, db_url: str, corpus: dict[str, str]) -> None:
        """A limit of one returns exactly one row."""
        vector = [
            float(part) for part in corpus["semantic_vector"].strip("[]").split(",")
        ]
        results = await VectorSearch(db_url).search(
            owner_type="information_unit", query_vector=vector, limit=1
        )
        assert len(results) == 1

    async def test_unknown_owner_type_returns_nothing(
        self, db_url: str, corpus: dict[str, str]
    ) -> None:
        """The owner_type filter is applied (no cross-type leakage)."""
        vector = [
            float(part) for part in corpus["semantic_vector"].strip("[]").split(",")
        ]
        results = await VectorSearch(db_url).search(
            owner_type="document", query_vector=vector, limit=10
        )
        assert results == []

    async def test_units_without_embedding_are_not_returned(
        self, db_url: str, corpus: dict[str, str]
    ) -> None:
        """A unit lacking an embedding row cannot match a vector search."""
        vector = [
            float(part) for part in corpus["semantic_vector"].strip("[]").split(",")
        ]
        owner_ids = {
            owner_id
            for owner_id, _ in await VectorSearch(db_url).search(
                owner_type="information_unit", query_vector=vector, limit=10
            )
        }
        assert corpus["isolated_unit"] not in owner_ids

