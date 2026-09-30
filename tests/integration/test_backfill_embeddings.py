"""§16.1 — le rattrapage ``scripts/backfill_embeddings.py`` sur PostgreSQL réel.

Le script est l'outil qui rend §16.2 utile *rétroactivement* : sans lui, toutes
les unités écrites avant L3.3 resteraient hors de l'index. Ces tests couvrent ses
trois propriétés contractuelles sur une vraie base :

* ``--dry-run`` : la liste exacte des candidats, **aucune** écriture, aucun appel
  de modèle ;
* **idempotence** : une seconde exécution ne repropose pas ce qui est déjà
  vectorisé et n'écrit aucun doublon (``ON CONFLICT DO NOTHING``) ;
* **dégradation explicite** : sans ``LLM_API_KEY`` rien n'est produit et le
  rapport nomme la variable ; sans base, rien n'est même tenté (code 2).

Le fournisseur est doublé par un ``httpx.MockTransport`` : aucun réseau.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy import text

from app.storage.database.engine import create_engine
from scripts.backfill_embeddings import (
    EXIT_DEGRADED,
    EXIT_NOTHING_TRIED,
    EXIT_OK,
    main,
)

DOCUMENT_ID = "DOC_01M3Q0000000000000000000AA"
SOURCE_ID = "SRC_01M3Q0000000000000000000AA"
REQUEST_ID = "REQ_01M3Q0000000000000000000AA"
UNIT_ID = "INF_01M3Q0000000000000000000BB"
UNIT_ALT = "INF_01M3Q0000000000000000000BC"
TEXT = "Le fournisseur a livré 12 kilos de café au client parisien"


def _seed(db_url: str) -> None:
    """Insert one document and two §11 units, and clear their vectors."""
    engine = create_engine(db_url)
    try:
        import asyncio

        async def _write() -> None:
            async with engine.begin() as connection:
                await connection.execute(
                    text("DELETE FROM embeddings WHERE owner_id = ANY(:ids)"),
                    {"ids": [UNIT_ID, UNIT_ALT]},
                )
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
                        ) VALUES (:id, :source_id, 'text/csv', 'hash', 's3://inis/x.csv', :rid)
                        ON CONFLICT (id) DO NOTHING
                        """
                    ),
                    {"id": DOCUMENT_ID, "source_id": SOURCE_ID, "rid": REQUEST_ID},
                )
                for unit_id in (UNIT_ID, UNIT_ALT):
                    await connection.execute(
                        text(
                            """
                            INSERT INTO information_units (
                                id, type, content, source_id, document_id, data_stage
                            ) VALUES (
                                :id, 'text', CAST(:content AS JSONB), :source_id,
                                :document_id, 'enriched'
                            )
                            ON CONFLICT (id) DO NOTHING
                            """
                        ),
                        {
                            "id": unit_id,
                            "content": json.dumps({"text": TEXT}),
                            "source_id": SOURCE_ID,
                            "document_id": DOCUMENT_ID,
                        },
                    )

        asyncio.run(_write())
    finally:
        import asyncio

        asyncio.run(engine.dispose())


def _count_vectors(db_url: str, owner_ids: list[str]) -> int:
    """Return how many vectors exist for *owner_ids*."""
    engine = create_engine(db_url)
    try:
        import asyncio

        async def _read() -> int:
            async with engine.connect() as connection:
                row = (
                    (
                        await connection.execute(
                            text(
                                "SELECT count(*) AS total FROM embeddings "
                                "WHERE owner_id = ANY(:ids)"
                            ),
                            {"ids": owner_ids},
                        )
                    )
                    .mappings()
                    .first()
                )
            return int(row["total"]) if row else 0

        return asyncio.run(_read())
    finally:
        import asyncio

        asyncio.run(engine.dispose())


def _install_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    """Answer every ``/embeddings`` call with 1536-wide vectors, offline."""
    original_init = httpx.AsyncClient.__init__

    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        count = len(payload["input"])
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": index, "embedding": [0.01] * 1536} for index in range(count)
                ],
                "usage": {"prompt_tokens": count},
            },
        )

    def _init(self: Any, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("transport", httpx.MockTransport(handler))
        original_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", _init)


def _report(path: Path) -> dict[str, Any]:
    """Return the JSON report the script wrote to *path*."""
    return json.loads(path.read_text(encoding="utf-8"))


#: The database container is shared by the whole session: every run of the script
#: is scoped to *this* test's request, so other tests' units cannot make the
#: assertions depend on the order the suite happens to run in.
SCOPED = ["--request-id", REQUEST_ID]


class TestDryRun:
    """« Regarde mais ne touche à rien » — et ne paie aucun appel."""

    def test_the_dry_run_lists_what_would_be_embedded(
        self, db_url: str, tmp_path: Path
    ) -> None:
        _seed(db_url)
        report_path = tmp_path / "report.json"

        code = main(
            ["--dsn", db_url, "--dry-run", "--limit", "10", "--report", str(report_path)]
            + SCOPED
        )

        report = _report(report_path)
        assert code == EXIT_OK
        assert report["dry_run"] is True
        assert set(report["candidate_ids"]) == {UNIT_ID, UNIT_ALT}
        assert report["embedded"] == 0
        assert report["persisted"] == 0

    def test_the_dry_run_writes_no_vector(self, db_url: str, tmp_path: Path) -> None:
        _seed(db_url)

        main(["--dsn", db_url, "--dry-run", "--limit", "10"] + SCOPED)

        assert _count_vectors(db_url, [UNIT_ID, UNIT_ALT]) == 0


class TestTheBackfillIsIdempotent:
    """Relancer le script ne duplique jamais un vecteur."""

    def test_a_first_run_embeds_everything_missing(
        self, db_url: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _seed(db_url)
        monkeypatch.setenv("LLM_API_KEY", "test-key")
        _install_transport(monkeypatch)
        report_path = tmp_path / "first.json"

        code = main(
            ["--dsn", db_url, "--limit", "10", "--report", str(report_path), "--batch-size", "1"]
            + SCOPED
        )

        report = _report(report_path)
        assert code == EXIT_OK
        assert report["candidates"] == 2
        assert report["embedded"] == 2
        assert report["persisted"] == 2
        assert _count_vectors(db_url, [UNIT_ID, UNIT_ALT]) == 2

    def test_a_second_run_has_nothing_left_to_do(
        self, db_url: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _seed(db_url)
        monkeypatch.setenv("LLM_API_KEY", "test-key")
        _install_transport(monkeypatch)
        main(["--dsn", db_url, "--limit", "10"] + SCOPED)
        before = _count_vectors(db_url, [UNIT_ID, UNIT_ALT])
        report_path = tmp_path / "second.json"

        code = main(["--dsn", db_url, "--limit", "10", "--report", str(report_path)] + SCOPED)

        report = _report(report_path)
        assert code == EXIT_OK
        assert report["candidates"] == 0
        assert report["persisted"] == 0
        assert _count_vectors(db_url, [UNIT_ID, UNIT_ALT]) == before == 2


class TestTheScriptSaysWhatItCouldNotDo:
    """§0.2/§25.2 — une dégradation se lit dans le rapport et dans le code de sortie."""

    def test_without_a_provider_nothing_is_produced_and_the_cause_is_named(
        self, db_url: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _seed(db_url)
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        report_path = tmp_path / "degraded.json"

        code = main(["--dsn", db_url, "--limit", "10", "--report", str(report_path)] + SCOPED)

        report = _report(report_path)
        assert code == EXIT_DEGRADED
        assert report["embedded"] == 0
        assert report["persisted"] == 0
        assert report["candidates"] == 2
        assert any("LLM_API_KEY" in line for line in report["limitations"])
        assert _count_vectors(db_url, [UNIT_ID, UNIT_ALT]) == 0

    def test_without_a_database_nothing_is_even_attempted(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("INIS_DATABASE_URL", raising=False)
        from app.storage.database.engine import set_default_engine

        set_default_engine(None)
        report_path = tmp_path / "no-db.json"

        code = main(["--dry-run", "--report", str(report_path)])

        report = _report(report_path)
        assert code == EXIT_NOTHING_TRIED
        assert any("INIS_DATABASE_URL" in line for line in report["limitations"])

    def test_the_report_exposes_the_counters_it_promised(
        self, db_url: str, tmp_path: Path
    ) -> None:
        """Les « métriques » du lot : des compteurs nommés, pas une métrique §34 inventée."""
        _seed(db_url)
        report_path = tmp_path / "shape.json"

        main(["--dsn", db_url, "--dry-run", "--report", str(report_path)] + SCOPED)

        report = _report(report_path)
        assert {
            "generated_at",
            "dry_run",
            "candidates",
            "embedded",
            "persisted",
            "skipped",
            "limitations",
            "dimension",
            "duration_seconds",
        } <= set(report)
        assert report["dimension"] == 1536

