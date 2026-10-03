"""§41.5 — le cache L2 PostgreSQL, écrit, relu, invalidé, et durable.

La table ``cache_entries`` existait depuis la révision ``0008`` et **personne
n'écrivait dedans** : le niveau L2 du cache §41.5 était un schéma sans
implémentation, donc une entrée mourait avec le processus. Ces tests exercent le
chemin réel (``CacheStore`` + ``PostgresCacheBackend``, celui qu'utilise l'étape
web du pipeline) contre le **vrai** PostgreSQL :

* ce qui est écrit ici est relu par un **autre interpréteur** — la preuve de
  durabilité exigée ;
* le pipeline lui-même ne rappelle pas le fournisseur web après vidage de L1 ;
* TTL, seuil de fraîcheur §41.5, invalidation par source et par namespace ;
* la ligne garde de quoi expliquer la réutilisation (namespace, niveau, source,
  instant d'obtention).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.storage.cache.cache_store import L2, CacheStore
from app.storage.cache.postgres_backend import PostgresCacheBackend
from app.storage.database.engine import set_default_engine
from app.storage.database.session import reset_session_maker
from app.storage.repositories.cache_repository import (
    CacheEntryRepository,
    cache_entries_table,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

#: The reader: a brand-new interpreter that only knows the namespace and parts.
READER_SCRIPT = """
import asyncio
import json
import os
import sys

sys.path.insert(0, os.getcwd())

from app.storage.cache.cache_store import CacheStore
from app.storage.cache.postgres_backend import PostgresCacheBackend


async def main() -> None:
    store = CacheStore(l2_async_backend=PostgresCacheBackend())
    parts = json.loads(os.environ["INIS_CACHE_PARTS"])
    value = await store.aget(os.environ["INIS_CACHE_NS"], *parts)
    print(json.dumps({"value": value, "stats": store.stats()}))


asyncio.run(main())
"""


@pytest.fixture(autouse=True)
def _database(db_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Bind both the storage layer and the cache backend to the test database."""
    monkeypatch.setenv("INIS_NULL_POOL", "1")
    set_default_engine(None)
    reset_session_maker()
    yield
    set_default_engine(None)
    reset_session_maker()


@pytest.fixture
def namespace() -> str:
    """A cache namespace unique to one test (no cross-test cache hit)."""
    return f"cachetest_{uuid.uuid4().hex[:12]}"


@pytest.fixture
async def store(db_url: str, monkeypatch: pytest.MonkeyPatch, namespace: str):
    """A store with the durable L2 level, cleaned up afterwards."""
    monkeypatch.setenv("INIS_DATABASE_URL", db_url)
    built = CacheStore(l2_async_backend=PostgresCacheBackend())
    backend = PostgresCacheBackend()
    try:
        yield built
    finally:
        await backend.ainvalidate_namespace(namespace)


def _read_with_a_new_process(
    db_url: str, namespace: str, parts: list[str], tmp_path: Path
) -> dict:
    """Read the cache from a **separate interpreter** and return its JSON."""
    script = tmp_path / "read_cache_l2.py"
    script.write_text(READER_SCRIPT, encoding="utf-8")
    completed = subprocess.run(
        [sys.executable, str(script)],
        cwd=REPO_ROOT,
        env={
            **os.environ,
            "INIS_DATABASE_URL": db_url,
            "INIS_CACHE_NS": namespace,
            "INIS_CACHE_PARTS": json.dumps(parts),
            "PYTHONIOENCODING": "utf-8",
        },
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout.strip().splitlines()[-1])


class TestTheEntrySurvivesTheProcess:
    """La preuve de durabilité : un autre interpréteur relit l'entrée."""

    async def test_an_entry_written_here_is_read_by_another_process(
        self, store: CacheStore, db_url: str, namespace: str, tmp_path: Path
    ) -> None:
        parts = ["quel est le nombre d'habitants de Paris", uuid.uuid4().hex[:8]]
        await store.aset(
            namespace,
            *parts,
            value=[{"title": "Paris", "snippet": "2 148 000 habitants"}],
            source_id="URL:https://exemple.invalid/paris",
            source_freshness=datetime.now(UTC),
        )
        assert store.l2_writes == 1, "l'écriture L2 doit avoir eu lieu"

        # Nouveau processus, même base : rien n'est partagé hors PostgreSQL.
        payload = _read_with_a_new_process(db_url, namespace, parts, tmp_path)

        assert payload["value"] == [{"title": "Paris", "snippet": "2 148 000 habitants"}]
        assert payload["stats"]["l2_enabled"] is True
        assert payload["stats"]["l2_promotions"] == 1

    async def test_the_row_keeps_what_explains_the_reuse(
        self, store: CacheStore, db_url: str, namespace: str
    ) -> None:
        """Namespace, niveau, source et instant d'obtention sont persistés."""
        from app.storage.cache.cache_store import make_cache_key
        from app.storage.database.engine import create_engine

        parts = ["origine de la donnée", uuid.uuid4().hex[:8]]
        await store.aset(
            namespace,
            *parts,
            value={"ok": True},
            source_id="URL:https://exemple.invalid/x",
            source_freshness=datetime.now(UTC),
        )

        engine = create_engine(db_url)
        try:
            row = await CacheEntryRepository.get(engine, make_cache_key(namespace, *parts))
        finally:
            await engine.dispose()

        assert row is not None
        assert row["namespace"] == namespace
        assert row["level"] == L2
        assert row["source_id"] == "URL:https://exemple.invalid/x"
        assert row["created_at"] is not None
        assert row["source_freshness"] is not None
        assert row["expires_at"] is not None, "le TTL §41.5 est porté par la ligne"


class TestTheContractIsEnforced:
    """TTL, seuil de fraîcheur, invalidation : le contrat §41.5, pas une variante."""

    async def test_an_expired_entry_is_not_reused_and_is_dropped(
        self, store: CacheStore, db_url: str, namespace: str
    ) -> None:
        from sqlalchemy import update

        from app.storage.cache.cache_store import make_cache_key
        from app.storage.database.engine import create_engine

        parts = ["entrée périmée"]
        await store.aset(namespace, *parts, value=["vieux"])
        store.clear()  # vide L1 : c'est bien L2 qui doit répondre

        engine = create_engine(db_url)
        try:
            # Le TTL est reculé dans le passé : l'entrée est périmée pour de bon.
            async with engine.begin() as conn:
                await conn.execute(
                    update(cache_entries_table)
                    .where(cache_entries_table.c.cache_key == make_cache_key(namespace, *parts))
                    .values(expires_at=datetime.now(UTC) - timedelta(seconds=5))
                )
            value = await store.aget(namespace, *parts)
            row = await CacheEntryRepository.get(engine, make_cache_key(namespace, *parts))
        finally:
            await engine.dispose()

        assert value is None, "une entrée périmée n'est jamais servie"
        assert row is None, "et elle est supprimée de L2, pas seulement ignorée"

    async def test_a_too_stale_entry_is_refused_by_the_freshness_rule(
        self, store: CacheStore, db_url: str, namespace: str
    ) -> None:
        """§41.5 : la fraîcheur de la source prime sur la présence en cache."""
        from app.storage.cache.cache_store import make_cache_key
        from app.storage.database.engine import create_engine

        parts = ["entrée trop vieille"]
        await store.aset(
            namespace,
            *parts,
            value=["périmé"],
            # Deux jours : au-delà du seuil de 24 h de la politique par défaut.
            source_freshness=datetime.now(UTC) - timedelta(days=2),
        )
        store.clear()

        value = await store.aget(namespace, *parts)

        assert value is None
        assert store.stale_rejections == 1
        engine = create_engine(db_url)
        try:
            row = await CacheEntryRepository.get(engine, make_cache_key(namespace, *parts))
        finally:
            await engine.dispose()
        assert row is None

    async def test_invalidation_by_source_drops_only_that_source(
        self, store: CacheStore, namespace: str
    ) -> None:
        await store.aset(
            namespace, "a", value=[1], source_id="URL:A", source_freshness=datetime.now(UTC)
        )
        await store.aset(
            namespace, "b", value=[2], source_id="URL:B", source_freshness=datetime.now(UTC)
        )
        store.clear()

        dropped = await store.ainvalidate_source("URL:A")

        assert dropped == 1
        assert await store.aget(namespace, "a") is None
        assert await store.aget(namespace, "b") == [2]

    async def test_invalidation_by_namespace_empties_only_that_namespace(
        self, store: CacheStore, namespace: str
    ) -> None:
        other = f"{namespace}_other"
        await store.aset(namespace, "x", value=[1], source_freshness=datetime.now(UTC))
        await store.aset(other, "x", value=[2], source_freshness=datetime.now(UTC))

        dropped = await store.ainvalidate_namespace(namespace)

        assert dropped >= 1
        assert await store.aget(namespace, "x") is None
        assert await store.aget(other, "x") == [2]
        await store.ainvalidate_namespace(other)

    async def test_purging_expired_entries_is_explicit(
        self, store: CacheStore, namespace: str
    ) -> None:
        await store.aset(namespace, "court", value=[1], ttl_seconds=1)
        purged = await store.apurge_expired(datetime.now(UTC) + timedelta(seconds=5))
        assert purged >= 1


class TestThePipelineUsesItForReal:
    """Le chemin réel : l'étape web du pipeline, pas un appel isolé."""

    async def test_the_web_search_is_served_from_l2_after_a_restart(
        self,
        db_url: str,
        namespace: str,
        mock_llm,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Le fournisseur n'est pas rappelé : L2 a servi la réponse, L1 vidé."""
        from unittest.mock import AsyncMock

        from app.api.v1.requests.pipeline_runner import PipelineRunner

        monkeypatch.setenv("INIS_DATABASE_URL", db_url)
        question = f"population de Paris {uuid.uuid4().hex[:8]}"
        provider = AsyncMock()
        provider.search = AsyncMock(
            return_value=[{"title": "Paris", "url": "https://exemple.invalid/p"}]
        )

        def _store() -> CacheStore:
            """A store whose L2 namespace belongs to this test."""
            return CacheStore(l2_async_backend=_NamespacedBackend(namespace))

        runner = PipelineRunner()
        runner._cache = _store()
        first = await runner._search_with_cache(provider, question, 5)
        assert first, "le premier appel interroge le fournisseur"

        # « Redémarrage » : L1 vidé, un nouveau runner relit L2.
        runner._cache.clear()
        restarted = PipelineRunner()
        restarted._cache = _store()
        second = await restarted._search_with_cache(provider, question, 5)

        assert provider.search.await_count == 1, "L2 doit avoir servi le second appel"
        assert second == first
        assert restarted._cache.stats()["l2_promotions"] >= 1


class _NamespacedBackend(PostgresCacheBackend):
    """The production backend, writing under this test's namespace only.

    The cache key is derived from the query and the provider, so two tests
    sharing a question would share an entry. Re-labelling the namespace makes
    the isolation explicit instead of relying on the queries being different.
    """

    def __init__(self, namespace: str) -> None:
        super().__init__()
        self._namespace = namespace

    async def aget(self, cache_key: str):  # type: ignore[override]
        return await super().aget(self._key(cache_key))

    async def aset(self, entry, ttl_seconds: int) -> bool:  # type: ignore[override]
        from dataclasses import replace

        return await super().aset(replace(entry, key=self._key(entry.key)), ttl_seconds)

    async def adelete(self, cache_key: str) -> bool:  # type: ignore[override]
        return await super().adelete(self._key(cache_key))

    def _key(self, cache_key: str) -> str:
        """Return the cache key moved into this test's namespace."""
        _, _, digest = cache_key.partition(":")
        return f"{self._namespace}:{digest}"
