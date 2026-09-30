"""§16.1/§16.2 — de la ligne écrite dans ``embeddings`` à la recherche vectorielle.

Ces tests exigent PostgreSQL + ``pgvector`` (testcontainers) : la colonne
``vector(1536)``, l'index HNSW et le cast ``CAST(:vector AS vector)`` n'existent
nulle part ailleurs. Sans Docker, ils sont **sautés proprement** — mais ils
restent la seule preuve que l'index est réellement alimenté : une ligne écrite
que §16.2 ne retrouve pas serait du poids mort.

Le scénario complet est couvert : une unité §11 est insérée, un vecteur est
produit par le générateur (routeur doublé), persisté, retrouvé par
``vector_search``, puis le rattrapage ne le repropose plus (idempotence).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
from sqlalchemy import text

from app.knowledge.embedding import (
    EMBEDDING_OWNER_TYPE,
    EmbeddingRecord,
    generate_embeddings,
    persist_embeddings,
)
from app.llm.router.model_router import EmbeddingResponse
from app.storage.database.engine import create_engine
from app.storage.repositories.embedding_repository import EmbeddingRepository
from app.tools.knowledge.vector_searcher import vector_search

DOCUMENT_ID = "DOC_01M3Q0000000000000000000AA"
SOURCE_ID = "SRC_01M3Q0000000000000000000AA"
REQUEST_ID = "REQ_01M3Q0000000000000000000AA"
UNIT_ID = "INF_01M3Q0000000000000000000BB"
UNIT_ALT = "INF_01M3Q0000000000000000000BC"
TEXT = "Le fournisseur a livré 12 kilos de café au client parisien"


@pytest.fixture
async def engine(db_url: str) -> AsyncIterator[Any]:
    """Yield an engine bound to the migrated PostgreSQL test database."""
    created = create_engine(db_url)
    await _cleanup(created)
    try:
        yield created
    finally:
        await _cleanup(created)
        await created.dispose()


async def _cleanup(engine: Any) -> None:
    """Remove what these tests wrote, so a re-run starts from the same state."""
    async with engine.begin() as connection:
        await connection.execute(
            text("DELETE FROM embeddings WHERE owner_id = ANY(:ids)"),
            {"ids": [UNIT_ID, UNIT_ALT]},
        )
        await connection.execute(
            text("DELETE FROM information_units WHERE id = ANY(:ids)"),
            {"ids": [UNIT_ID, UNIT_ALT]},
        )
        await connection.execute(
            text("DELETE FROM documents WHERE id = :id"), {"id": DOCUMENT_ID}
        )
        await connection.execute(text("DELETE FROM sources WHERE id = :id"), {"id": SOURCE_ID})


async def _seed(engine: Any) -> None:
    """Insert the §9/§11 material a vector can be attached to."""
    async with engine.begin() as connection:
        await connection.execute(
            text(
                """
                INSERT INTO sources (id, url, source_type, data_stage)
                VALUES (:id, 'https://example.test/rapport', 'web', 'raw')
                ON CONFLICT (id) DO NOTHING
                """
            ),
            {"id": SOURCE_ID},
        )
        await connection.execute(
            text(
                """
                INSERT INTO documents (
                    id, source_id, mime_type, content_hash, storage_ref, request_id
                ) VALUES (
                    :id, :source_id, 'text/csv', 'hash', 's3://inis/x.csv', :request_id
                )
                ON CONFLICT (id) DO NOTHING
                """
            ),
            {"id": DOCUMENT_ID, "source_id": SOURCE_ID, "request_id": REQUEST_ID},
        )
        for unit_id in (UNIT_ID, UNIT_ALT):
            await connection.execute(
                text(
                    """
                    INSERT INTO information_units (
                        id, type, content, source_id, document_id, data_stage
                    ) VALUES (
                        :id, 'text', CAST(:content AS JSONB), :source_id, :document_id,
                        'enriched'
                    )
                    ON CONFLICT (id) DO NOTHING
                    """
                ),
                {
                    "id": unit_id,
                    "content": '{"text": "' + TEXT + '"}',
                    "source_id": SOURCE_ID,
                    "document_id": DOCUMENT_ID,
                },
            )


class _StubRouter:
    """Router double: one 1536-wide vector per text (the width of the column)."""

    async def embed(
        self,
        texts: Any,
        *,
        model: str | None = None,
        dimension: int = 1536,
        batch_size: int | None = None,
    ) -> EmbeddingResponse:
        return EmbeddingResponse(
            vectors=[[0.01] * 1536 for _ in texts],
            model=model or "stub-embedding-model",
            input_tokens=len(list(texts)),
            latency_ms=1,
        )


class TestTheVectorIsStoredAsTheColumnExpects:
    """§16.1 — la ligne écrite est relisible, avec son modèle et sa largeur."""

    async def test_a_vector_is_written_with_its_model_and_width(self, engine: Any) -> None:
        await _seed(engine)
        record = EmbeddingRecord(
            owner_id=UNIT_ID, vector=(0.5,) * 1536, model="stub-embedding-model"
        )

        written, limitations = await persist_embeddings([record], engine=engine)

        assert written == 1
        assert limitations == []
        async with engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT model, owner_type, vector_dims(vector) AS dimensions,
                                   metadata
                            FROM embeddings WHERE owner_id = :owner_id
                            """
                        ),
                        {"owner_id": UNIT_ID},
                    )
                )
                .mappings()
                .first()
            )

        assert row is not None
        assert row["model"] == "stub-embedding-model"
        assert row["dimensions"] == 1536
        assert row["owner_type"] == EMBEDDING_OWNER_TYPE

    async def test_the_same_identifier_twice_is_written_once(self, engine: Any) -> None:
        await _seed(engine)
        record = EmbeddingRecord(owner_id=UNIT_ID, vector=(0.25,) * 1536, model="m")

        first, _ = await persist_embeddings([record], engine=engine)
        second, _ = await persist_embeddings([record], engine=engine)

        assert first == 1
        assert second == 0
        assert await EmbeddingRepository.count(engine) >= 1

    async def test_a_row_without_model_is_refused(self, engine: Any) -> None:
        with pytest.raises(ValueError):
            await EmbeddingRepository.insert_many(
                engine, [{"owner_id": UNIT_ID, "vector": [0.1], "model": ""}]
            )

    async def test_the_listing_returns_the_owner_entries(self, engine: Any) -> None:
        await _seed(engine)
        await persist_embeddings(
            [EmbeddingRecord(owner_id=UNIT_ID, vector=(0.5,) * 1536, model="m")],
            engine=engine,
        )

        rows = await EmbeddingRepository.list_for_owner(engine, EMBEDDING_OWNER_TYPE, UNIT_ID)

        assert [row["owner_id"] for row in rows] == [UNIT_ID]
        assert rows[0]["dimensions"] == 1536


class TestTheIndexIsReallyUsable:
    """§16.2 — un vecteur que le chercheur ne retrouve pas ne sert à rien."""

    async def test_the_semantic_search_finds_the_indexed_unit(self, engine: Any) -> None:
        await _seed(engine)
        await persist_embeddings(
            [
                EmbeddingRecord(
                    owner_id=UNIT_ID,
                    vector=(1.0,) + (0.0,) * 1535,
                    model="stub-embedding-model",
                    metadata={"text_hash": "abc"},
                )
            ],
            engine=engine,
        )

        units = await vector_search(
            [1.0] + [0.0] * 1535, limit=5, engine=engine, owner_type=EMBEDDING_OWNER_TYPE
        )
        identifiers = [unit.information_id for unit in units]

        # The container is shared by the session: the proof is that *this* unit is
        # found, and found first — its vector is exactly the query.
        assert identifiers[0] == UNIT_ID
        assert UNIT_ID in identifiers
        assert units[0].provenance["retrieval"] == "vector"

    async def test_the_backfill_only_sees_the_units_without_a_vector(self, engine: Any) -> None:
        await _seed(engine)

        before = await EmbeddingRepository.list_units_without_embedding(
            engine,
            owner_type=EMBEDDING_OWNER_TYPE,
            limit=10,
            request_id=REQUEST_ID,
        )
        await persist_embeddings(
            [EmbeddingRecord(owner_id=UNIT_ID, vector=(0.5,) * 1536, model="m")],
            engine=engine,
        )
        after = await EmbeddingRepository.list_units_without_embedding(
            engine,
            owner_type=EMBEDDING_OWNER_TYPE,
            limit=10,
            request_id=REQUEST_ID,
        )

        assert {unit["information_id"] for unit in before} == {UNIT_ID, UNIT_ALT}
        assert {unit["information_id"] for unit in after} == {UNIT_ALT}

    async def test_the_backfill_can_be_restricted_to_one_request(self, engine: Any) -> None:
        await _seed(engine)

        scoped = await EmbeddingRepository.list_units_without_embedding(
            engine,
            owner_type=EMBEDDING_OWNER_TYPE,
            limit=10,
            request_id="REQ_does_not_exist",
        )

        assert scoped == []

    async def test_generation_then_persistence_leaves_nothing_to_backfill(
        self, engine: Any
    ) -> None:
        await _seed(engine)
        units = await EmbeddingRepository.list_units_without_embedding(
            engine,
            owner_type=EMBEDDING_OWNER_TYPE,
            limit=10,
            request_id=REQUEST_ID,
        )

        outcome = await generate_embeddings(
            units, router=_StubRouter(), request_id=REQUEST_ID
        )
        written, limitations = await persist_embeddings(outcome.records, engine=engine)

        assert outcome.vector_count == len(units) == 2
        assert written == len(units)
        assert limitations == []
        remaining = await EmbeddingRepository.list_units_without_embedding(
            engine,
            owner_type=EMBEDDING_OWNER_TYPE,
            limit=10,
            request_id=REQUEST_ID,
        )
        assert remaining == []

