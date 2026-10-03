"""§16.2/ADR 004 — les poids 0.6 / 0.4 vérifiés au chiffre près, sur pgvector réel.

L'ADR 004 fixe ``0.6 * score_vectoriel + 0.4 * score_lexical`` **et** sa
précondition : chaque sous-score est ramené dans ``[0, 1]`` avant pondération.
Avant L4, ni l'un ni l'autre n'était vérifiable : le ``ts_rank`` brut (non borné)
était pondéré contre une similarité cosinus (bornée), et la requête ne rendait
qu'un ``final_score`` opaque.

Ce module sème **son propre** corpus (des mots rares que rien d'autre ne
contient), de sorte que le maximum de chaque moitié lui appartienne : le score
attendu est alors calculable à la main, et non « au moins supérieur à ».

Trois unités, trois scores attendus ::

    meilleure des deux moitiés : 0.6 × 1.0 + 0.4 × 1.0 = 1.0
    sémantique seule          : 0.6 × 1.0 + 0.4 × 0.0 = 0.6
    lexicale seule            : 0.6 × 0.0 + 0.4 × 1.0 = 0.4
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text

from app.storage.database.engine import create_engine
from app.storage.search.hybrid_search import HybridSearch

SOURCE_ID = "SRC_01M3Q0000000000000000000WA"
UNIT_BOTH = "INF_01M3Q0000000000000000000W1"
UNIT_SEMANTIC = "INF_01M3Q0000000000000000000W2"
UNIT_LEXICAL = "INF_01M3Q0000000000000000000W3"
UNIT_IDS = (UNIT_BOTH, UNIT_SEMANTIC, UNIT_LEXICAL)

#: Mots volontairement rares : seules ces unités-là les contiennent. Les deux
#: unités lexicales portent le **même** texte, donc le même ``ts_rank`` : elles
#: saturent toutes deux la moitié lexicale, et c'est bien le poids — non un
#: écart de rang — que les scores attendus mesurent.
QUERY = "quasiconvexity zephyrometer"
TEXT_BOTH = "quasiconvexity zephyrometer"
TEXT_LEXICAL = "quasiconvexity zephyrometer"
TEXT_SEMANTIC = "an unrelated sentence about tides and harbours"

DIMENSION = 1536
VECTOR_HOT = [1.0] + [0.0] * (DIMENSION - 1)
VECTOR_ORTHOGONAL = [0.0, 1.0] + [0.0] * (DIMENSION - 2)

#: ``pgvector`` stocke des ``float4`` : une égalité exacte serait un test qui
#: échoue pour une raison qui n'appartient pas au contrat.
TOLERANCE = 1e-6


def _literal(vector: list[float]) -> str:
    """Return the pgvector literal of *vector*."""
    return "[" + ",".join(map(str, vector)) + "]"


@pytest.fixture
async def corpus(db_url: str) -> AsyncIterator[None]:
    """Seed three units whose maxima belong to this module, then remove them."""
    engine = create_engine(db_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO sources (id, url, source_type, data_stage)
                    VALUES (:id, 'https://example.test/weights', 'web', 'raw')
                    ON CONFLICT (id) DO NOTHING
                    """
                ),
                {"id": SOURCE_ID},
            )
            for unit_id, unit_text, vector in (
                (UNIT_BOTH, TEXT_BOTH, VECTOR_HOT),
                (UNIT_SEMANTIC, TEXT_SEMANTIC, VECTOR_HOT),
                (UNIT_LEXICAL, TEXT_LEXICAL, VECTOR_ORTHOGONAL),
            ):
                await connection.execute(
                    text(
                        """
                        INSERT INTO information_units
                            (id, type, content, source_id, data_stage, search_vector)
                        VALUES (
                            :id, 'text', CAST(:content AS JSONB), :source_id, 'derived',
                            to_tsvector(:text)
                        )
                        ON CONFLICT (id) DO UPDATE
                        SET content = EXCLUDED.content,
                            search_vector = EXCLUDED.search_vector
                        """
                    ),
                    {
                        "id": unit_id,
                        "content": '{"text": "' + unit_text + '"}',
                        "source_id": SOURCE_ID,
                        "text": unit_text,
                    },
                )
                await connection.execute(
                    text(
                        """
                        INSERT INTO embeddings
                            (embedding_id, owner_type, owner_id, model, vector)
                        VALUES (
                            CAST(md5(:owner_id) AS uuid), 'information_unit', :owner_id,
                            'weights-test-model', CAST(:vector AS vector)
                        )
                        ON CONFLICT (embedding_id) DO NOTHING
                        """
                    ),
                    {"owner_id": unit_id, "vector": _literal(vector)},
                )
        yield
    finally:
        async with engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM embeddings WHERE owner_id = ANY(:ids)"),
                {"ids": list(UNIT_IDS)},
            )
            await connection.execute(
                text("DELETE FROM information_units WHERE id = ANY(:ids)"),
                {"ids": list(UNIT_IDS)},
            )
            await connection.execute(
                text("DELETE FROM sources WHERE id = :id"), {"id": SOURCE_ID}
            )
        await engine.dispose()


async def _scores(db_url: str) -> dict[str, float]:
    """Return the fused score of this module's units, by identifier."""
    outcome = await HybridSearch(db_url).search_outcome(
        query=QUERY, query_vector=VECTOR_HOT, limit=10
    )
    assert outcome.mode == "hybrid"
    return {
        str(row["owner_id"]): float(row["final_score"])
        for row in outcome.rows
        if str(row["owner_id"]) in UNIT_IDS
    }


class TestTheAdr004WeightsHoldOnRealData:
    """ADR 004 — ``0.6 × sémantique + 0.4 × lexical``, chaque moitié dans [0, 1]."""

    async def test_a_unit_best_on_both_halves_scores_one(
        self, db_url: str, corpus: None
    ) -> None:
        scores = await _scores(db_url)

        assert scores[UNIT_BOTH] == pytest.approx(1.0, abs=TOLERANCE)

    async def test_a_semantic_only_unit_scores_the_semantic_weight(
        self, db_url: str, corpus: None
    ) -> None:
        scores = await _scores(db_url)

        assert scores[UNIT_SEMANTIC] == pytest.approx(0.6, abs=TOLERANCE)

    async def test_a_lexical_only_unit_scores_the_lexical_weight(
        self, db_url: str, corpus: None
    ) -> None:
        scores = await _scores(db_url)

        assert scores[UNIT_LEXICAL] == pytest.approx(0.4, abs=TOLERANCE)

    async def test_the_order_follows_the_formula(self, db_url: str, corpus: None) -> None:
        scores = await _scores(db_url)

        assert scores[UNIT_BOTH] > scores[UNIT_SEMANTIC] > scores[UNIT_LEXICAL]

    async def test_each_sub_score_is_normalised_into_the_unit_interval(
        self, db_url: str, corpus: None
    ) -> None:
        """Un ``ts_rank`` brut n'est pas borné : la normalisation est le contrat."""
        outcome = await HybridSearch(db_url).search_outcome(
            query=QUERY, query_vector=VECTOR_HOT, limit=10
        )

        for row in outcome.rows:
            assert 0.0 <= float(row["semantic_score"]) <= 1.0
            assert 0.0 <= float(row["lexical_score"]) <= 1.0
            assert 0.0 <= float(row["final_score"]) <= 1.0

    async def test_the_weights_are_readable_on_the_search(self, db_url: str) -> None:
        search = HybridSearch(db_url)

        assert search.weights == {"semantic": 0.6, "lexical": 0.4}

