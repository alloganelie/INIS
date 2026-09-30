"""§36.7/§24.1 — la moitié « base » du critère de sortie L2, sur PostgreSQL réel.

La chaîne exercée est celle qui manquait : une requête `request_type="data"` nomme
une source PostgreSQL par ``constraints.source_preferences`` (§7), le pipeline lit
la table par ``postgres_query`` **sur le DSN du vault** (§41.4) — jamais sur la
base d'INIS — et son colis doit contenir le ``Dataset`` des lignes, une unité §11
par ligne localisée en ``row``, la source de type ``database``, les transformations
§12.1 du connecteur Postgres, et **aucune** recherche web (§7, C4).

Sont vérifiés ici, contre le vrai PostgreSQL : les octets lus sont ceux de la
table (pas de mémoire, pas de convention), un échec est nommé et rien n'est
inventé, le ``Dataset`` livré reste consultable (§27) et les unités livrées sont
persistées avec leur provenance.

Conteneur requis (pgvector) : le test est ignoré sans Docker.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import text

from app.api.v1.requests.pipeline_runner import PipelineRunner
from app.domain.value_objects.ulid import ULID
from app.knowledge.ingestion.database_material import load_database_material_for_request
from app.storage.database.engine import create_engine, set_default_engine
from app.storage.database.session import reset_session_maker
from app.storage.repositories.dataset_repository import DatasetRepository

OBJECTIVE = "Analyse les agents de notre base analytics"
TABLE = "inis_e2e_agents"
PREFERENCE = f"postgres:analytics#{TABLE}"
STORAGE_REF = f"postgres://analytics/{TABLE}"
ROWS = [
    {"agent_id": "A-1", "city": "Paris", "status": "active"},
    {"agent_id": "A-2", "city": "Berlin", "status": "inactive"},
    {"agent_id": "A-3", "city": "Lyon", "status": "active"},
]


@pytest.fixture(autouse=True)
def _fresh_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rebuild the process-wide engine in the loop of the current test (§33.2)."""
    monkeypatch.setenv("INIS_NULL_POOL", "1")
    set_default_engine(None)
    reset_session_maker()
    yield
    set_default_engine(None)
    reset_session_maker()


async def _seed_table(engine: Any) -> None:
    """Create the source table of this run and fill it with known rows."""
    async with engine.begin() as conn:
        await conn.execute(text(f"DROP TABLE IF EXISTS {TABLE}"))
        await conn.execute(
            text(
                f"CREATE TABLE {TABLE} ("
                "agent_id text, city text, status text, secret text)"
            )
        )
        for index, row in enumerate(ROWS, start=1):
            await conn.execute(
                text(
                    f"INSERT INTO {TABLE} (agent_id, city, status, secret) "
                    "VALUES (:agent_id, :city, :status, :secret)"
                ),
                {**row, "secret": f"s3cr3t-{index}"},
            )


async def _run_scenario(db_url: str) -> tuple[dict[str, Any], Any]:
    """Seed the source, run the pipeline, and return the delivery and engine."""
    engine = create_engine(db_url)
    await _seed_table(engine)
    delivery = await PipelineRunner().run(
        ULID.new("REQ_"),
        {
            "objective": OBJECTIVE,
            "request_type": "data",
            "constraints": {"source_preferences": [PREFERENCE]},
        },
    )
    return delivery, engine


def _stages(delivery: dict[str, Any]) -> list[tuple[str, str]]:
    """Return the (stage, tool) pairs of the delivered §12.1 transformations."""
    return [
        (item["parameters"]["stage"], item["tool"])
        for item in delivery["transformations"]
    ]


def _db_units(delivery: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the delivered units read by ``postgres_query``."""
    return [
        unit
        for unit in delivery["information_units"]
        if unit.get("provenance", {}).get("method") == "app.tools.database.postgres_query"
    ]
def test_a_data_request_reads_the_named_table(
    db_url: str, mock_llm: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§7/§36.7 — la table nommée entre dans le colis, sans recherche web."""
    monkeypatch.setenv("INIS_DATABASE_URL", db_url)
    monkeypatch.setenv("INIS_CRED_ANALYTICS", json.dumps({"dsn": db_url}))
    mock_llm.configure('{"summary": "Base lue.", "findings": []}')
    search = AsyncMock(return_value=[])
    monkeypatch.setattr(
        "app.connectors.web.provider_router.ProviderRouter.search", search
    )

    async def _scenario() -> dict[str, Any]:
        delivery, engine = await _run_scenario(db_url)
        await engine.dispose()
        return delivery

    delivery = asyncio.run(_scenario())

    assert search.await_count == 0
    assert len(delivery["datasets"]) == 1
    dataset = delivery["datasets"][0]
    assert dataset["row_count"] == 3
    assert dataset["storage_ref"] == STORAGE_REF
    assert dataset["dataset_schema"] == {
        "agent_id": "string",
        "city": "string",
        "secret": "string",
        "status": "string",
    }

    units = _db_units(delivery)
    assert len(units) == 3
    assert sorted(unit["location"]["row"] for unit in units) == [1, 2, 3]
    for unit in units:
        assert unit["location"]["kind"] == "row"
        assert unit["dataset_id"] == dataset["dataset_id"]
        assert unit["provenance"]["extracted_from"] == STORAGE_REF
        assert unit["context"]["origin"] == "database_query"

    sources = {source["source_id"]: source for source in delivery["sources"]}
    assert sources[dataset["source_id"]]["source_type"] == "database"
    assert sources[dataset["source_id"]]["url"] == STORAGE_REF

    stages = _stages(delivery)
    assert ("raw", "postgres_query") in stages
    assert ("normalized", "postgres_query") in stages
    assert delivery["provenance"]["request_type"] == "data"


def test_the_rows_come_from_the_table_not_from_memory(
    db_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§0.2 — une ligne ajoutée entre deux lectures est vue à la seconde."""
    monkeypatch.setenv("INIS_DATABASE_URL", db_url)
    monkeypatch.setenv("INIS_CRED_ANALYTICS", json.dumps({"dsn": db_url}))

    async def _read_twice() -> tuple[int, int]:
        engine = create_engine(db_url)
        try:
            await _seed_table(engine)
            payload = {"constraints": {"source_preferences": [PREFERENCE]}}
            first = await load_database_material_for_request(
                payload, request_id=ULID.new("REQ_"), engine=engine
            )
            async with engine.begin() as conn:
                await conn.execute(
                    text(
                        f"INSERT INTO {TABLE} (agent_id, city, status, secret) "
                        "VALUES ('A-4', 'Nantes', 'active', 's3cr3t-4')"
                    )
                )
            second = await load_database_material_for_request(
                payload, request_id=ULID.new("REQ_"), engine=engine
            )
            assert first is not None and second is not None
            return first.row_count, second.row_count
        finally:
            await engine.dispose()

    first_count, second_count = asyncio.run(_read_twice())

    assert (first_count, second_count) == (3, 4)


def test_a_missing_table_is_named_and_nothing_is_delivered(
    db_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§25.2 — une table absente est un échec nommé, pas un dataset vide."""
    monkeypatch.setenv("INIS_DATABASE_URL", db_url)
    monkeypatch.setenv("INIS_CRED_ANALYTICS", json.dumps({"dsn": db_url}))

    async def _read() -> Any:
        engine = create_engine(db_url)
        try:
            await _seed_table(engine)
            return await load_database_material_for_request(
                {"constraints": {"source_preferences": ["postgres:analytics#table_absente"]}},
                request_id=ULID.new("REQ_"),
                engine=engine,
            )
        finally:
            await engine.dispose()

    material = asyncio.run(_read())

    assert material is not None
    assert material.dataset is None
    assert material.units == ()
    assert material.has_material is False
    assert len(material.limitations) == 1
    assert "n'a pas pu être lue" in material.limitations[0]


def test_an_absent_vault_entry_names_the_variable_an_operator_must_set(
    db_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§41.4 — sans entrée de vault, la livraison nomme la variable à poser."""
    monkeypatch.setenv("INIS_DATABASE_URL", db_url)
    monkeypatch.delenv("INIS_CRED_ANALYTICS", raising=False)

    async def _read() -> Any:
        engine = create_engine(db_url)
        try:
            await _seed_table(engine)
            return await load_database_material_for_request(
                {"constraints": {"source_preferences": [PREFERENCE]}},
                request_id=ULID.new("REQ_"),
            )
        finally:
            await engine.dispose()

    material = asyncio.run(_read())

    assert material is not None
    assert material.dataset is None
    assert "INIS_CRED_ANALYTICS" in material.limitations[0]
def test_the_delivered_dataset_is_consultable(
    db_url: str, mock_llm: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§11/§27 — l'identifiant ``DATA_`` publié existe en base après le run."""
    monkeypatch.setenv("INIS_DATABASE_URL", db_url)
    monkeypatch.setenv("INIS_CRED_ANALYTICS", json.dumps({"dsn": db_url}))
    mock_llm.configure('{"summary": "Base lue.", "findings": []}')

    async def _scenario() -> tuple[dict[str, Any], dict[str, Any] | None]:
        delivery, engine = await _run_scenario(db_url)
        try:
            dataset_id = delivery["datasets"][0]["dataset_id"]
            return delivery, await DatasetRepository.get(engine, dataset_id)
        finally:
            await engine.dispose()

    delivery, stored = asyncio.run(_scenario())

    assert stored is not None
    assert stored["dataset_id"] == delivery["datasets"][0]["dataset_id"]
    assert stored["row_count"] == 3
    assert stored["storage_ref"] == STORAGE_REF
    assert stored["name"] == "analytics#inis_e2e_agents"
    assert stored["request_id"] == delivery["request_id"]


def test_the_delivered_units_are_persisted_with_their_provenance(
    db_url: str, mock_llm: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§11/§12.1 — une unité livrée reste expliquable après le run."""
    monkeypatch.setenv("INIS_DATABASE_URL", db_url)
    monkeypatch.setenv("INIS_CRED_ANALYTICS", json.dumps({"dsn": db_url}))
    mock_llm.configure('{"summary": "Base lue.", "findings": []}')

    async def _scenario() -> tuple[list[str], list[dict[str, Any]]]:
        delivery, engine = await _run_scenario(db_url)
        try:
            unit_ids = [unit["information_id"] for unit in _db_units(delivery)]
            async with engine.connect() as conn:
                result = await conn.execute(
                    text(
                        "SELECT id, raw_reference, provenance FROM information_units "
                        "WHERE id = ANY(:ids)"
                    ),
                    {"ids": unit_ids},
                )
                return unit_ids, [dict(row) for row in result.mappings().all()]
        finally:
            await engine.dispose()

    unit_ids, rows = asyncio.run(_scenario())

    assert len(unit_ids) == 3
    assert len(rows) == 3
    for row in rows:
        provenance = row["provenance"]
        provenance = json.loads(provenance) if isinstance(provenance, str) else provenance
        raw = row["raw_reference"]
        raw = json.loads(raw) if isinstance(raw, str) else raw
        assert provenance["method"] == "app.tools.database.postgres_query"
        assert raw["table"] == TABLE
        assert raw["location"]["kind"] == "row"


def test_the_secrets_of_the_vault_are_not_reported(
    db_url: str, mock_llm: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§19/§0.2 — le colis ne recopie aucun secret du vault ni de la base."""
    monkeypatch.setenv("INIS_DATABASE_URL", db_url)
    monkeypatch.setenv("INIS_CRED_ANALYTICS", json.dumps({"dsn": db_url}))
    mock_llm.configure('{"summary": "Base lue.", "findings": []}')

    async def _scenario() -> dict[str, Any]:
        delivery, engine = await _run_scenario(db_url)
        await engine.dispose()
        return delivery

    delivery = asyncio.run(_scenario())
    serialised = json.dumps(delivery, default=str)

    assert db_url not in serialised
    assert "INIS_CRED_ANALYTICS" not in serialised


def test_a_table_identifier_carrying_sql_cannot_reach_the_database(
    db_url: str, mock_llm: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§1.2/§19 — l'identifiant interpolé est refusé : la table survit au run."""
    monkeypatch.setenv("INIS_DATABASE_URL", db_url)
    monkeypatch.setenv("INIS_CRED_ANALYTICS", json.dumps({"dsn": db_url}))
    mock_llm.configure('{"summary": "Refus.", "findings": []}')
    search = AsyncMock(return_value=[])
    monkeypatch.setattr(
        "app.connectors.web.provider_router.ProviderRouter.search", search
    )

    async def _scenario() -> dict[str, Any]:
        engine = create_engine(db_url)
        try:
            await _seed_table(engine)
            delivery = await PipelineRunner().run(
                ULID.new("REQ_"),
                {
                    "objective": OBJECTIVE,
                    "request_type": "data",
                    "constraints": {
                        "source_preferences": [
                            f"postgres:analytics#{TABLE}; DROP TABLE {TABLE}"
                        ]
                    },
                },
            )
            async with engine.connect() as conn:
                row = (
                    await conn.execute(
                        text(
                            "SELECT count(*) AS total FROM information_schema.tables "
                            "WHERE table_schema = 'public' AND table_name = :name"
                        ),
                        {"name": TABLE},
                    )
                ).mappings().first()
            assert int((row or {}).get("total") or 0) == 1
            return delivery
        finally:
            await engine.dispose()

    delivery = asyncio.run(_scenario())

    assert delivery["datasets"] == []
    assert any("inutilisable" in text_value for text_value in delivery["limitations"])
    assert search.await_count == 0