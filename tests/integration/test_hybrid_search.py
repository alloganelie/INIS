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

    async def test_final_score_is_the_adr_004_weighted_sum(
        self, db_url: str, corpus: dict[str, str]
    ) -> None:
        """§16.2/ADR 004 — ``final = 0.6 × sémantique + 0.4 × lexical``, au chiffre près.

        Les deux sous-scores sont exposés (L4) : le poids appliqué est donc
        vérifiable au lieu d'être cru sur parole, et chaque sous-score est bien
        ramené dans ``[0, 1]`` avant pondération. La tolérance est ``1e-6`` :
        ``pgvector`` stocke des ``float4``, une égalité exacte serait un test
        qui échoue pour une raison qui n'appartient pas au contrat.
        """
        results = await HybridSearch(db_url).search(
            query=LEXICAL_QUERY,
            query_vector=as_float_list(corpus["semantic_vector"]),
            limit=10,
        )
        assert results
        for row in results:
            assert set(row) == {
                "owner_id",
                "semantic_score",
                "lexical_score",
                "final_score",
            }
            assert 0.0 <= row["semantic_score"] <= 1.0
            assert 0.0 <= row["lexical_score"] <= 1.0
            assert row["final_score"] == pytest.approx(
                0.6 * row["semantic_score"] + 0.4 * row["lexical_score"], abs=1e-6
            )
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

    async def test_an_unusable_driver_is_stated_not_hidden(self) -> None:
        """§16.2/§0.2 — le mode réel est exposé, jamais présenté comme hybride."""
        outcome = await HybridSearch("nosuchdriver://localhost/db").search_outcome(
            query="anything", query_vector=[0.0] * 4
        )

        assert outcome.mode == "unavailable"
        assert outcome.rows == ()
        assert any("indisponible" in line for line in outcome.limitations)

    async def test_without_a_query_vector_the_mode_is_lexical_only(
        self, db_url: str, corpus: dict[str, str]
    ) -> None:
        """§17.1 — sans vecteur de requête, la recherche le dit au lieu de le taire."""
        outcome = await HybridSearch(db_url).search_outcome(query=LEXICAL_QUERY, limit=10)

        assert outcome.mode == "lexical_only"
        assert any("lexicale seule" in line for line in outcome.limitations)
        assert corpus["lexical_unit"] in outcome.ids()
        assert all(row["semantic_score"] == 0.0 for row in outcome.rows)

    @pytest.mark.parametrize(
        ("semantic", "lexical"),
        [(-0.1, 0.4), (0.6, -0.1), (0.0, 0.0)],
    )
    async def test_impossible_weights_are_refused(
        self, semantic: float, lexical: float
    ) -> None:
        """Un poids négatif ou deux poids nuls ne peuvent rien classer : refus."""
        with pytest.raises(ValueError):
            HybridSearch("postgresql://test", semantic_weight=semantic, lexical_weight=lexical)

