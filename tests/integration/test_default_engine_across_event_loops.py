"""§41.14 / piège P14 — l'engine par défaut ne survit pas à un changement de boucle.

Un pool asyncpg appartient à la **boucle** qui a ouvert ses connexions.
``get_default_engine()`` mettait son moteur en cache **par URL seulement** : la
deuxième boucle d'événements (ce que fait ``pytest-asyncio`` : une boucle par
test, ou un test synchrone puis ``asyncio.run(...)``) récupérait le pool de la
première et échouait — soit ``RuntimeError: Event loop is closed``, soit le
``TimeoutError`` de connexion d'``asyncpg`` en attendant une boucle morte.

C'était la cause de l'instabilité de la suite complète : un test **différent** à
chaque exécution, tous verts isolément. Le moteur est désormais recréé quand la
boucle change, comme le prescrit le plan (« créer l'engine dans la boucle qui
l'utilise »).

Ces tests n'utilisent **aucune** des mitigations documentées (``INIS_NULL_POOL=1``,
``set_default_engine(None)`` avant la seconde boucle) : s'ils les utilisaient, ils
ne prouveraient rien. Le premier échoue sur le code d'avant le correctif.
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import text

from app.storage.database.engine import get_default_engine, set_default_engine


def test_the_default_engine_survives_a_new_event_loop(
    db_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Deux boucles successives utilisent l'engine par défaut sans erreur."""
    monkeypatch.setenv("INIS_DATABASE_URL", db_url)
    monkeypatch.delenv("INIS_NULL_POOL", raising=False)
    set_default_engine(None)
    values: list[int] = []

    async def _read_once() -> None:
        """Read one row through the default engine of the *current* loop."""
        engine = get_default_engine()
        assert engine is not None
        async with engine.connect() as connection:
            values.append((await connection.execute(text("SELECT 1"))).scalar_one())

    try:
        asyncio.run(_read_once())
        asyncio.run(_read_once())
    finally:
        set_default_engine(None)

    assert values == [1, 1]


def test_the_default_engine_is_shared_inside_one_loop(
    db_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Contre-preuve : dans une même boucle, le moteur reste bien mis en cache."""
    monkeypatch.setenv("INIS_DATABASE_URL", db_url)
    set_default_engine(None)
    seen: list[bool] = []

    async def _same_engine_twice() -> None:
        """Two lookups inside one loop must return the very same object."""
        seen.append(get_default_engine() is get_default_engine())

    try:
        asyncio.run(_same_engine_twice())
    finally:
        set_default_engine(None)

    assert seen == [True]


def test_the_engine_is_rebuilt_when_the_url_changes(
    db_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le cache reste indexé par URL : changer d'URL reconstruit le moteur."""
    other_url = db_url.rsplit("/", 1)[0] + "/inis_other_database"
    monkeypatch.setenv("INIS_DATABASE_URL", db_url)
    set_default_engine(None)
    first = get_default_engine()
    try:
        assert get_default_engine() is first
        monkeypatch.setenv("INIS_DATABASE_URL", other_url)
        assert get_default_engine() is not first
    finally:
        set_default_engine(None)
