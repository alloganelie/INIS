"""§41.5 L3 / §16.1 — réutiliser un embedding déjà calculé, sans jamais mentir.

La spec définit le troisième niveau : « L3 — pgvector : embeddings persistants
(invalidés par nouvelle version) ». Ce n'est donc pas une troisième paire
clé/valeur à TTL, c'est la table ``embeddings`` (§16.1) — déjà écrite par le
générateur, déjà lue par la recherche §16.2 — que le ``CacheStore`` lit pour
éviter un appel au fournisseur.

Ces tests tournent contre le **vrai** PostgreSQL/pgvector et vérifient les huit
points demandés, dont les trois refus qui rendent un faux hit impossible :
mauvais propriétaire, mauvais modèle, mauvaise largeur.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import pytest
from sqlalchemy import text

from app.knowledge.embedding.embeddings_generator import (
    EMBEDDING_OWNER_TYPE,
    EmbeddingOutcome,
    embedding_cache_key,
    embedding_row_id,
    generate_embeddings,
    persist_embeddings,
)
from app.llm.router.model_router import EMBEDDING_DIMENSION
from app.storage.cache.cache_store import CacheStore
from app.storage.cache.vector_backend import PgVectorCacheBackend
from app.storage.database.engine import create_engine, set_default_engine
from app.storage.database.session import reset_session_maker

MODEL = "fake-embedding-model"
#: La largeur de ``embeddings.vector`` (``0003``) : pgvector refuse toute autre,
#: donc un test qui persiste doit utiliser **celle de la colonne** — c'est aussi
#: ce qui rend le refus « dimensions incompatibles » observable.
DIMENSION = EMBEDDING_DIMENSION

#: Propriétaires dont **ce module** a écrit un vecteur, vidés après chaque test :
#: ``embeddings`` est partagée, donc un test qui écrit doit nettoyer derrière lui.
_WRITTEN_OWNERS: list[str] = []


class CountingRouter:
    """Fournisseur double qui **compte** les appels : c'est la mesure du gain."""

    def __init__(self, model: str = MODEL, dimension: int = DIMENSION) -> None:
        self.calls = 0
        self.texts: list[list[str]] = []
        self._model = model
        self._dimension = dimension

    def embeddings_model(self) -> str:
        """Return the model this router answers with (§22)."""
        return self._model

    async def embed(
        self, texts: list[str], *, model: str | None = None, dimension: int = EMBEDDING_DIMENSION,
        batch_size: int | None = None,
    ) -> Any:
        """Answer with a deterministic vector per text, and count the call."""
        self.calls += 1
        self.texts.append(list(texts))
        from app.llm.router.model_router import EmbeddingResponse

        vectors = [
            [float(index + 1) for index in range(self._dimension)] for _ in texts
        ]
        return EmbeddingResponse(
            vectors=vectors,
            model=self._model,
            input_tokens=len(texts) * 3,
            latency_ms=1,
            raw={},
        )


def _unit(unit_id: str, text_value: str, *, source_id: str = "SRC_01M3Q0000000000000000000AA") -> dict:
    """Build one §11 unit carrying a traceable text."""
    return {
        "information_id": unit_id,
        "type": "text",
        "content": {"text": text_value},
        "source_id": source_id,
        "document_id": None,
        "data_stage": "normalized",
    }


@pytest.fixture(autouse=True)
def _fresh_engine(db_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Bind the process to the migrated pgvector database."""
    monkeypatch.setenv("INIS_NULL_POOL", "1")
    set_default_engine(None)
    reset_session_maker()
    yield
    set_default_engine(None)
    reset_session_maker()


@pytest.fixture(autouse=True)
def _clean_embeddings(db_url: str) -> Any:
    """Remove the vectors this test wrote, so the shared table stays clean.

    ``embeddings`` est une table **partagée** : y laisser des vecteurs de test
    change le classement d'autres tests (le corpus de ``test_pgvector.py``
    interroge la même table avec une limite, et un vecteur oublié ici en
    évinçait une unité attendue). Un test qui écrit doit donc rendre la table
    telle qu'il l'a trouvée.
    """
    _WRITTEN_OWNERS.clear()
    yield
    owners = list(_WRITTEN_OWNERS)
    _WRITTEN_OWNERS.clear()
    if not owners:
        return
    engine = create_engine(db_url)
    try:
        for owner_id in owners:
            asyncio.run(_delete_owner(engine, owner_id))
    finally:
        asyncio.run(engine.dispose())


async def _delete_owner(engine: Any, owner_id: str) -> None:
    """Delete every vector stored for one owner."""
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "DELETE FROM embeddings WHERE owner_type = :t AND owner_id = :o"
            ),
            {"t": EMBEDDING_OWNER_TYPE, "o": owner_id},
        )


def _cache(db_url: str) -> CacheStore:
    """Return a store whose L3 level reads the real ``embeddings`` table."""
    return CacheStore(l3_async_backend=PgVectorCacheBackend(create_engine(db_url)))


async def _generate_and_persist(
    db_url: str,
    units: list[dict],
    router: CountingRouter,
    cache: CacheStore,
) -> EmbeddingOutcome:
    """Run the real generation (with L3) and persist what it produced."""
    outcome = await generate_embeddings(
        units, router=router, model=MODEL, dimension=DIMENSION, cache=cache
    )
    engine = create_engine(db_url)
    try:
        written, limitations = await persist_embeddings(outcome.records, engine=engine)
    finally:
        await engine.dispose()
    assert not limitations, f"la persistance doit aboutir sans limite : {limitations}"
    assert written == len(outcome.records), "chaque vecteur produit devient une ligne"
    _WRITTEN_OWNERS.extend(record.owner_id for record in outcome.records)
    return outcome


async def _row_count(db_url: str, owner_id: str) -> int:
    """Count the stored vectors of one owner."""
    engine = create_engine(db_url)
    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text(
                    "SELECT count(*) FROM embeddings WHERE owner_type = :t AND owner_id = :o"
                ),
                {"t": EMBEDDING_OWNER_TYPE, "o": owner_id},
            )
            return int(result.scalar_one())
    finally:
        await engine.dispose()


class TestTheFirstComputationCallsTheProvider:
    """1/2 — premier calcul : provider appelé ; second : servi par L3."""

    def test_the_first_run_calls_the_provider_and_stores_the_vector(
        self, db_url: str
    ) -> None:
        unit_id = f"INF_{uuid.uuid4().hex[:26]}"
        units = [_unit(unit_id, "Le fournisseur a livré 12 kilos de café.")]
        router = CountingRouter()
        cache = _cache(db_url)

        first = asyncio.run(_generate_and_persist(db_url, units, router, cache))

        assert router.calls == 1, "le premier calcul doit appeler le fournisseur"
        assert first.reused == 0
        assert first.vector_count == 1
        assert asyncio.run(_row_count(db_url, unit_id)) == 1
        # L'entrée L3 garde de quoi expliquer un futur hit.
        metadata = first.records[0].metadata
        assert metadata["cache"]["hit"] is False
        assert metadata["source_id"] == "SRC_01M3Q0000000000000000000AA"

    def test_the_second_run_is_served_by_l3_and_never_calls_the_provider(
        self, db_url: str
    ) -> None:
        """Le provider n'est pas rappelé : le vecteur vient de pgvector."""
        unit_id = f"INF_{uuid.uuid4().hex[:26]}"
        units = [_unit(unit_id, "Le fournisseur a livré 12 kilos de café.")]
        warming = CountingRouter()
        asyncio.run(_generate_and_persist(db_url, units, warming, _cache(db_url)))
        assert warming.calls == 1

        router = CountingRouter()
        second = asyncio.run(
            generate_embeddings(
                units, router=router, model=MODEL, dimension=DIMENSION, cache=_cache(db_url)
            )
        )

        assert router.calls == 0, "un vecteur en L3 ne doit pas rappeler le provider"
        assert second.reused == 1
        assert second.records[0].metadata["cache"]["hit"] is True
        assert second.records[0].metadata["cache"]["level"] == "L3"
        # Le vecteur réutilisé est **celui de la base**, pas une valeur neuve.
        assert second.records[0].vector == tuple(float(i + 1) for i in range(DIMENSION))
        assert asyncio.run(_row_count(db_url, unit_id)) == 1, "aucune ligne en double"


class TestDurabilityAndInvalidation:
    """3/4/5 — persistance après redémarrage, entrée refusée, invalidation."""

    def test_a_new_process_reuses_the_stored_vector(self, db_url: str) -> None:
        """Persistance : un « autre processus » (cache et moteur neufs) réutilise."""
        unit_id = f"INF_{uuid.uuid4().hex[:26]}"
        units = [_unit(unit_id, "Texte durable du cache L3.")]
        asyncio.run(_generate_and_persist(db_url, units, CountingRouter(), _cache(db_url)))

        # « Redémarrage » : nouveau moteur, nouveau backend, nouveau cache.
        set_default_engine(None)
        reset_session_maker()
        router = CountingRouter()
        restarted = asyncio.run(
            generate_embeddings(
                units, router=router, model=MODEL, dimension=DIMENSION, cache=_cache(db_url)
            )
        )

        assert router.calls == 0, "la base porte le vecteur, pas la mémoire"
        assert restarted.reused == 1

    def test_a_stored_row_whose_text_changed_is_not_a_hit(self, db_url: str) -> None:
        """Invalidation par le texte : le texte révisé n'est pas servi par l'ancien."""
        unit_id = f"INF_{uuid.uuid4().hex[:26]}"
        asyncio.run(
            _generate_and_persist(
                db_url, [_unit(unit_id, "Texte initial de l'unité.")], CountingRouter(), _cache(db_url)
            )
        )

        router = CountingRouter()
        revised = asyncio.run(
            generate_embeddings(
                [_unit(unit_id, "Texte INITIAL de l'unité, révisé.")],
                router=router,
                model=MODEL,
                dimension=DIMENSION,
                cache=_cache(db_url),
            )
        )

        assert router.calls == 1, "un texte différent doit être recalculé"
        assert revised.reused == 0

    def test_a_new_version_of_the_unit_with_new_text_recomputes(
        self, db_url: str
    ) -> None:
        """§41.5 « invalidés par nouvelle version » : le texte révisé recalcule.

        L'identité d'un vecteur est ``(propriétaire, texte, modèle, largeur)`` :
        un embedding est une **fonction du texte** et du modèle, pas de la version
        de l'unité. Une nouvelle version qui change le texte produit donc un autre
        vecteur (l'ancien n'est jamais servi pour le texte révisé) ; une nouvelle
        version qui ne change pas le texte réutilise légitimement le même vecteur,
        qui serait identique de toute façon. La version de l'unité entre par
        ailleurs dans la **clé de cache** L3, qui sert à expliquer un hit.
        """
        unit_id = f"INF_{uuid.uuid4().hex[:26]}"
        asyncio.run(
            _generate_and_persist(
                db_url,
                [_unit(unit_id, "Texte de la première version de l'unité.")],
                CountingRouter(),
                _cache(db_url),
            )
        )

        router = CountingRouter()
        revised = asyncio.run(
            generate_embeddings(
                [_unit(unit_id, "Texte de la DEUXIÈME version de l'unité.")],
                router=router,
                model=MODEL,
                dimension=DIMENSION,
                cache=_cache(db_url),
            )
        )

        assert router.calls == 1, "un texte révisé n'est pas servi par l'ancien vecteur"
        assert revised.reused == 0


class TestAFalseHitIsImpossible:
    """6/7 — un autre propriétaire, un autre modèle ou une autre largeur : pas de hit."""

    def test_another_owner_does_not_borrow_the_vector(self, db_url: str) -> None:
        """Deux unités, même texte : deux lignes, aucun emprunt croisé."""
        first = f"INF_{uuid.uuid4().hex[:26]}"
        second = f"INF_{uuid.uuid4().hex[:26]}"
        text_value = "Texte strictement identique pour deux unités."
        asyncio.run(
            _generate_and_persist(db_url, [_unit(first, text_value)], CountingRouter(), _cache(db_url))
        )

        router = CountingRouter()
        outcome = asyncio.run(
            generate_embeddings(
                [_unit(second, text_value)],
                router=router,
                model=MODEL,
                dimension=DIMENSION,
                cache=_cache(db_url),
            )
        )

        assert router.calls == 1, "un autre propriétaire n'a pas de vecteur : il calcule"
        assert outcome.reused == 0
        assert embedding_row_id(first, "x", MODEL, DIMENSION) != embedding_row_id(
            second, "x", MODEL, DIMENSION
        )

    def test_another_model_is_not_a_hit(self, db_url: str) -> None:
        """Un vecteur d'un autre modèle est un vecteur d'un autre espace."""
        unit_id = f"INF_{uuid.uuid4().hex[:26]}"
        text_value = "Texte pour changer de modèle."
        asyncio.run(
            _generate_and_persist(db_url, [_unit(unit_id, text_value)], CountingRouter(), _cache(db_url))
        )
        backend = PgVectorCacheBackend(create_engine(db_url))
        from app.core.hashing import sha256_hex

        found = asyncio.run(
            CacheStore(l3_async_backend=backend).aget_l3(
                "embedding",
                embedding_cache_key(unit_id, sha256_hex(text_value), "autre-modele", DIMENSION, None),
                owner_id=unit_id,
                text_hash=sha256_hex(text_value),
                model="autre-modele",
                dimension=DIMENSION,
            )
        )

        assert found is None, "un autre modèle ne peut pas retomber sur ce vecteur"

    def test_another_dimension_is_not_a_hit(self, db_url: str) -> None:
        """Une autre largeur ne doit jamais être servie (elle ne se compare pas)."""
        unit_id = f"INF_{uuid.uuid4().hex[:26]}"
        text_value = "Texte pour changer de largeur."
        asyncio.run(
            _generate_and_persist(db_url, [_unit(unit_id, text_value)], CountingRouter(), _cache(db_url))
        )
        backend = PgVectorCacheBackend(create_engine(db_url))
        from app.core.hashing import sha256_hex

        other_dimension = DIMENSION - 1
        found = asyncio.run(
            CacheStore(l3_async_backend=backend).aget_l3(
                "embedding",
                embedding_cache_key(unit_id, sha256_hex(text_value), MODEL, other_dimension, None),
                owner_id=unit_id,
                text_hash=sha256_hex(text_value),
                model=MODEL,
                dimension=other_dimension,
            )
        )

        assert found is None, "aucune ligne de cette largeur n'existe pour ce texte"


class TestTheReusedVectorStaysTraceable:
    """8 — un hit reste traçable, et n'est pas une information nouvelle."""

    def test_the_hit_keeps_its_provenance(self, db_url: str) -> None:
        """Le vecteur réutilisé porte la source, le document et l'empreinte du texte."""
        unit_id = f"INF_{uuid.uuid4().hex[:26]}"
        text_value = "Un texte dont le vecteur doit rester traçable."
        units = [_unit(unit_id, text_value)]
        asyncio.run(_generate_and_persist(db_url, units, CountingRouter(), _cache(db_url)))

        outcome = asyncio.run(
            generate_embeddings(
                units, router=CountingRouter(), model=MODEL, dimension=DIMENSION, cache=_cache(db_url)
            )
        )

        metadata = outcome.records[0].metadata
        assert outcome.reused == 1
        assert metadata["cache"]["hit"] is True
        assert metadata["cache"]["text_hash"], "l'empreinte du texte explique le hit"
        assert metadata["source_id"] == "SRC_01M3Q0000000000000000000AA"
        assert metadata["data_stage"] == "normalized"
        # Le hit ne crée pas de donnée : le nombre de lignes reste celui du premier run.
        assert asyncio.run(_row_count(db_url, unit_id)) == 1

    def test_a_partial_cache_still_names_the_failure(self, db_url: str) -> None:
        """Un hit partiel ne masque pas l'échec du reste : la limite est dite."""
        cached_id = f"INF_{uuid.uuid4().hex[:26]}"
        fresh_id = f"INF_{uuid.uuid4().hex[:26]}"
        asyncio.run(
            _generate_and_persist(
                db_url, [_unit(cached_id, "Texte déjà indexé.")], CountingRouter(), _cache(db_url)
            )
        )

        class _FailingRouter(CountingRouter):
            """Le second calcul échoue : le colis ne doit pas en être privé."""

            async def embed(self, texts: list[str], **kwargs: Any) -> Any:
                self.calls += 1
                from app.core.errors import InfrastructureError

                raise InfrastructureError("fournisseur indisponible")

        router = _FailingRouter()
        outcome = asyncio.run(
            generate_embeddings(
                [_unit(cached_id, "Texte déjà indexé."), _unit(fresh_id, "Texte jamais indexé.")],
                router=router,
                model=MODEL,
                dimension=DIMENSION,
                cache=_cache(db_url),
            )
        )

        assert router.calls == 1, "seul le vecteur absent est demandé au fournisseur"
        assert outcome.reused == 1, "le vecteur déjà indexé reste livré"
        assert outcome.vector_count == 1, "aucun vecteur n'est inventé pour l'unité en échec"
        assert any("partiellement" in item for item in outcome.limitations), (
            "l'échec partiel doit être dit, pas absorbé"
        )
        assert outcome.records[0].metadata["cache"]["hit"] is True