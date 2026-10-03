"""§16.1/§41.12 — ce que le générateur de vecteurs produit, et sous quelles règles.

Le ``embeddings`` de la migration ``0003`` et son index HNSW existaient depuis la
V1 sans qu'aucune ligne n'y soit jamais écrite (C13). Ce fichier verrouille ce
que l'étape qui les remplit doit garantir :

* **un vecteur par unité embeddable**, dans l'ordre soumis, avec le modèle qui
  l'a produit et une métadonnée qui dit quel texte a été vectorisé (son
  empreinte, jamais son contenu dupliqué) ;
* **les unités non embeddables sont nommées** (sans identifiant, sans texte) au
  lieu d'être vectorisées vides ;
* **un appel tracé** : une trace §41.12 par étape, avec ``task_type=embedding``
  et **l'empreinte** de l'entrée, jamais l'entrée ;
* la ligne écrite est **stockable telle quelle** : ``embedding_id`` UUID (le type
  de la colonne), ``owner_type`` aligné sur le chercheur §16.2, littéral pgvector
  valide.

Le routeur est doublé : aucun réseau, aucun modèle réel.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.core.hashing import sha256_hex
from app.knowledge.embedding import (
    EMBEDDING_DIMENSION,
    EMBEDDING_OWNER_TYPE,
    EmbeddingOutcome,
    EmbeddingRecord,
    generate_embeddings,
    vector_literal,
)
from app.llm.router.model_router import EmbeddingResponse
from app.llm.tracing.llm_trace_writer import LLMTraceWriter
from app.tools.knowledge.vector_searcher import OWNER_TYPE

DIMENSION = 4
UNIT_ONE = "INF_01M3Q0000000000000000000BB"
UNIT_TWO = "INF_01M3Q0000000000000000000BC"
UNIT_THREE = "INF_01M3Q0000000000000000000BD"


class FakeRouter:
    """Router double: one deterministic vector per text, in order."""

    def __init__(self, *, dimension: int = DIMENSION, model: str = "fake-embedding") -> None:
        self.model = model
        self.calls: list[list[str]] = []
        self._dimension = dimension

    async def embed(
        self,
        texts: Any,
        *,
        model: str | None = None,
        dimension: int = EMBEDDING_DIMENSION,
        batch_size: int | None = None,
    ) -> EmbeddingResponse:
        self.calls.append(list(texts))
        return EmbeddingResponse(
            vectors=[[float(index + 1)] * self._dimension for index, _ in enumerate(texts)],
            model=model or self.model,
            input_tokens=7 * len(texts),
            latency_ms=5,
        )


def _unit(
    unit_id: str = UNIT_ONE,
    text: str = "Le fournisseur a livré 12 kilos de café",
    *,
    data_stage: str = "enriched",
) -> dict[str, Any]:
    """Return one §11 unit whose analysable text is *text*."""
    return {
        "information_id": unit_id,
        "type": "text",
        "content": {"text": text},
        "source_id": "SRC_01M3Q0000000000000000000AA",
        "document_id": "DOC_01M3Q0000000000000000000AA",
        "data_stage": data_stage,
    }


class TestRecordShape:
    """La ligne produite entre telle quelle dans la colonne ``vector``."""

    def test_the_owner_type_is_the_one_the_searcher_reads(self) -> None:
        """Un vecteur que §16.2 ne voit pas serait du poids mort."""
        assert EMBEDDING_OWNER_TYPE == OWNER_TYPE

    def test_the_identifier_is_a_uuid_not_a_ulid(self) -> None:
        """Le type de la colonne (``0003``) est ``UUID``."""
        record = EmbeddingRecord(owner_id=UNIT_ONE, vector=(0.5,), model="m")

        assert str(uuid.UUID(record.embedding_id)) == record.embedding_id

    def test_the_row_carries_what_the_table_expects(self) -> None:
        record = EmbeddingRecord(
            owner_id=UNIT_ONE,
            vector=(0.25, 0.5),
            model="text-embedding-3-small",
            metadata={"text_hash": "abc"},
        ).to_row()

        assert set(record) == {
            "embedding_id",
            "owner_type",
            "owner_id",
            "model",
            "vector",
            "metadata",
        }
        assert record["owner_type"] == EMBEDDING_OWNER_TYPE
        assert record["vector"] == "[0.25,0.5]"
        assert record["metadata"] == {"text_hash": "abc"}

    def test_the_vector_literal_is_the_pgvector_one(self) -> None:
        assert vector_literal([1, 0.5, -0.25]) == "[1.0,0.5,-0.25]"


class TestGeneration:
    """Un vecteur par unité embeddable, dans l'ordre, avec le modèle tracé."""

    async def test_every_embeddable_unit_gets_one_vector(self) -> None:
        router = FakeRouter()
        outcome = await generate_embeddings(
            [_unit(UNIT_ONE), _unit(UNIT_TWO, "The supplier shipped 5 kilos")],
            router=router,
            dimension=DIMENSION,
        )

        assert isinstance(outcome, EmbeddingOutcome)
        assert outcome.owner_ids == [UNIT_ONE, UNIT_TWO]
        assert outcome.model == "fake-embedding"
        assert len(router.calls[0]) == 2

    async def test_the_text_embedded_is_the_text_stored(self) -> None:
        text = "Le fournisseur a livré 12 kilos de café"
        outcome = await generate_embeddings(
            [_unit(text=text)], router=FakeRouter(), dimension=DIMENSION
        )

        assert outcome.records[0].metadata["text_hash"] == sha256_hex(text)
        assert outcome.records[0].metadata["chars"] == len(text)

    async def test_the_metadata_says_where_the_vector_comes_from(self) -> None:
        outcome = await generate_embeddings(
            [_unit()], router=FakeRouter(), dimension=DIMENSION, request_id="REQ_1"
        )
        metadata = outcome.records[0].metadata

        assert metadata["source_id"] == "SRC_01M3Q0000000000000000000AA"
        assert metadata["document_id"] == "DOC_01M3Q0000000000000000000AA"
        assert metadata["data_stage"] == "enriched"
        assert metadata["request_id"] == "REQ_1"

    async def test_the_content_is_never_duplicated_in_the_metadata(self) -> None:
        """Le colis porte déjà le texte : le recopier doublerait le stockage."""
        outcome = await generate_embeddings([_unit()], router=FakeRouter(), dimension=DIMENSION)

        assert "text" not in outcome.records[0].metadata


class TestWhatIsLeftOutIsNamed:
    """Une unité vide n'est jamais vectorisée vide : elle est nommée."""

    async def test_a_unit_without_text_is_skipped_and_named(self) -> None:
        outcome = await generate_embeddings(
            [_unit(UNIT_ONE), _unit(UNIT_TWO, "")],
            router=FakeRouter(),
            dimension=DIMENSION,
        )

        assert outcome.owner_ids == [UNIT_ONE]
        assert outcome.skipped == ({"information_id": UNIT_TWO, "reason": "no_text"},)

    async def test_a_unit_without_identifier_is_skipped_and_named(self) -> None:
        unit = _unit()
        unit.pop("information_id")

        outcome = await generate_embeddings([unit], router=FakeRouter(), dimension=DIMENSION)

        assert outcome.records == ()
        assert outcome.skipped == ({"information_id": "", "reason": "no_identifier"},)

    async def test_a_colis_without_embeddable_unit_states_the_gap(self) -> None:
        outcome = await generate_embeddings(
            [_unit(UNIT_ONE, "")], router=FakeRouter(), dimension=DIMENSION
        )

        assert outcome.records == ()
        assert any("Aucun vecteur" in line for line in outcome.limitations)
        assert outcome.lineage() is None

    async def test_nothing_asked_means_nothing_stated(self) -> None:
        outcome = await generate_embeddings([], router=FakeRouter(), dimension=DIMENSION)

        assert outcome.records == ()
        assert outcome.limitations == ()

    async def test_the_lineage_carries_the_model_and_the_width(self) -> None:
        outcome = await generate_embeddings(
            [_unit(UNIT_ONE)], router=FakeRouter(), dimension=DIMENSION
        )

        assert outcome.lineage() == {
            "unit_ids": [UNIT_ONE],
            "model": "fake-embedding",
            "dimension": DIMENSION,
            "vectors": 1,
            # §41.5 — le lignage dit désormais quel niveau a servi le vecteur.
            "reused": 0,
            "computed": 1,
            "skipped": 0,
            "tokens": 7,
        }


class TestTheCallIsTraced:
    """§41.12 — une décision de modèle se relit ; l'entrée, elle, n'est pas stockée."""

    async def test_one_trace_is_written_for_the_step(self) -> None:
        writer = LLMTraceWriter()

        await generate_embeddings(
            [_unit()],
            router=FakeRouter(),
            dimension=DIMENSION,
            trace_writer=writer,
            request_id="REQ_1",
            step_id="embedding",
        )

        traces = writer.list_traces()
        assert len(traces) == 1
        assert traces[0]["task_type"] == "embedding"
        assert traces[0]["request_id"] == "REQ_1"
        assert traces[0]["model_used"] == "fake-embedding"

    async def test_the_prompt_is_hashed_never_stored(self) -> None:
        writer = LLMTraceWriter()

        await generate_embeddings(
            [_unit(text="secret interne")],
            router=FakeRouter(),
            dimension=DIMENSION,
            trace_writer=writer,
        )

        stored = writer.list_traces()[0]
        assert stored["prompt_hash"] == sha256_hex("secret interne")
        assert "secret interne" not in str(stored)

    async def test_a_degraded_trace_is_stated_rather_than_hidden(self) -> None:
        class BrokenWriter:
            """Writer that refuses every trace, to test the stated gap."""

            def build_trace(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
                return {}

            def write(self, trace: Any) -> None:
                raise RuntimeError("trace store unavailable")

        outcome = await generate_embeddings(
            [_unit()], router=FakeRouter(), dimension=DIMENSION, trace_writer=BrokenWriter()
        )

        assert outcome.vector_count == 1
        assert any("§41.12" in line for line in outcome.limitations)

