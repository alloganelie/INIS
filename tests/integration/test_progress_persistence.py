"""§41.1 — la progression survit à la perte de l'état mémoire.

Le contrat exige que « le demandeur puisse interroger la progression **sans
attendre la livraison finale** » (``GET /v1/requests/{id}/progress``). La
progression était servie depuis le ``RequestLifecycle`` en mémoire : au
redémarrage du worker, elle disparaissait alors que la requête, elle, restait en
base. Ces tests prouvent qu'elle est désormais **persistée** et relue depuis
PostgreSQL, et qu'elle reste **cohérente avec le point de reprise** :

* un run interrompu garde la progression qu'il avait réellement atteinte ;
* un run terminé n'apparaît jamais « en cours » ;
* aucune progression n'est inventée pour une requête qui n'en a pas.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.v1.requests.pipeline_runner import PipelineRunner, pipeline_runner
from app.domain.value_objects.ulid import ULID
from app.main import app
from app.storage.database.engine import create_engine, set_default_engine
from app.storage.database.session import reset_session_maker
from app.storage.repositories.checkpoint_repository import CheckpointRepository
from app.storage.repositories.progress_repository import ProgressRepository
from app.storage.repositories.request_repository import RequestRepository

client = TestClient(app)

OBJECTIVE = "Analyse la progression persistée d'une requête longue"


@pytest.fixture(autouse=True)
def _fresh_engine(db_url: str, monkeypatch: pytest.MonkeyPatch) -> str:
    """Bind the process to the migrated test database."""
    monkeypatch.setenv("INIS_DATABASE_URL", db_url)
    monkeypatch.setenv("INIS_NULL_POOL", "1")
    set_default_engine(None)
    reset_session_maker()
    yield db_url
    set_default_engine(None)
    reset_session_maker()


def _persist_request(db_url: str, request_id: str) -> None:
    """Insert the ``requests`` row the pipeline expects to find."""

    async def insert() -> None:
        engine = create_engine(db_url)
        try:
            await RequestRepository.create(
                engine,
                {
                    "request_id": request_id,
                    "request_type": "research",
                    "objective": OBJECTIVE,
                },
            )
        finally:
            await engine.dispose()

    asyncio.run(insert())


def _interrupted_run(db_url: str, request_id: str) -> dict[str, Any]:
    """Run the pipeline, then kill the process at the first committed step.

    L'interruption est **réelle** (`os._exit`), comme celle validée pour la
    reprise : elle laisse exactement ce qu'un crash laisse derrière lui.
    """
    import json
    import os
    import subprocess
    import sys
    import tempfile
    from pathlib import Path

    script = Path(tempfile.mkdtemp()) / "interrupted_progress.py"
    script.write_text(
        """
import asyncio
import json
import os
import sys

sys.path.insert(0, os.getcwd())


async def main() -> None:
    from app.api.v1.requests.pipeline_runner import PipelineRunner
    from app.storage.database.engine import set_default_engine
    from app.storage.database.session import reset_session_maker

    os.environ["INIS_NULL_POOL"] = "1"
    set_default_engine(None)
    reset_session_maker()

    original = PipelineRunner._checkpoint_step

    async def commit_then_die(self, request_id, **kwargs):
        await original(self, request_id, **kwargs)
        if kwargs.get("step_index", 0) >= 1:
            os._exit(137)

    PipelineRunner._checkpoint_step = commit_then_die
    payload = json.loads(os.environ["INIS_REQUEST_PAYLOAD"])
    await PipelineRunner().run(os.environ["INIS_REQUEST_ID"], payload)
    print("NOT_KILLED")


try:
    asyncio.run(main())
except BaseException:
    print("CHILD_FAILED")
""",
        encoding="utf-8",
    )
    completed = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(Path(__file__).resolve().parents[2]),
        env={
            **os.environ,
            "INIS_DATABASE_URL": db_url,
            "INIS_REQUEST_ID": request_id,
            "INIS_REQUEST_PAYLOAD": json.dumps(
                {"objective": OBJECTIVE, "request_type": "research"}
            ),
            "PYTHONIOENCODING": "utf-8",
        },
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    return {"stdout": completed.stdout, "stderr": completed.stderr}


async def _progress_row(db_url: str, request_id: str) -> dict[str, Any] | None:
    """Read the persisted progress row of one request."""
    engine = create_engine(db_url)
    try:
        return await ProgressRepository.get(engine, request_id)
    finally:
        await engine.dispose()


async def _checkpoint(db_url: str, request_id: str) -> dict[str, Any] | None:
    """Read the §41.1 checkpoint of one request."""
    engine = create_engine(db_url)
    try:
        return await CheckpointRepository.get(engine, request_id)
    finally:
        await engine.dispose()


class TestAnInterruptedRunKeepsItsRealProgress:
    """Le crash laisse la progression réellement atteinte, et elle se relit."""

    def test_the_progress_of_an_interrupted_run_is_persisted_and_readable(
        self, _fresh_engine: str
    ) -> None:
        """Perte de l'état mémoire, puis reconstruction depuis PostgreSQL."""
        db_url = _fresh_engine
        request_id = ULID.new("REQ_")
        _persist_request(db_url, request_id)

        output = _interrupted_run(db_url, request_id)
        assert "NOT_KILLED" not in output["stdout"], output["stderr"][-400:]

        row = asyncio.run(_progress_row(db_url, request_id))
        assert row is not None, "un run interrompu doit laisser sa progression en base"
        assert row["steps_done"] >= 1, "l'étape committée avant l'arrêt est comptée"
        assert row["steps_total"] >= row["steps_done"]
        assert row["partial_findings_available"] is True
        assert row["current_step"] not in ("DELIVERY",), (
            "un run interrompu n'est pas terminé"
        )

        # Perte **totale** de l'état en mémoire : le singleton est vidé, donc la
        # route ne peut plus répondre que depuis PostgreSQL.
        pipeline_runner.reset_state()
        assert pipeline_runner.progress(request_id) is None

        response = client.get(f"/v1/requests/{request_id}/progress")

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["steps_done"] == row["steps_done"]
        assert body["steps_total"] == row["steps_total"]
        assert body["partial_findings_available"] is True

    def test_the_progress_agrees_with_the_checkpoint(self, _fresh_engine: str) -> None:
        """Progression et point de reprise racontent le **même** fait."""
        db_url = _fresh_engine
        request_id = ULID.new("REQ_")
        _persist_request(db_url, request_id)
        _interrupted_run(db_url, request_id)

        row = asyncio.run(_progress_row(db_url, request_id))
        checkpoint = asyncio.run(_checkpoint(db_url, request_id))

        assert row is not None and checkpoint is not None
        assert row["steps_done"] == checkpoint["step_index"], (
            "le nombre d'étapes faites est celui du point de reprise"
        )
        assert checkpoint["resumable"] is True
        assert row["current_step"] != "DELIVERY"


class TestAFinishedRunNeverLooksInProgress:
    """Aucun état « terminé » inventé, aucun run fini présenté comme en cours."""

    def test_a_finished_run_reports_delivery_and_the_plan_total(
        self, _fresh_engine: str, mock_llm: Any
    ) -> None:
        db_url = _fresh_engine
        request_id = ULID.new("REQ_")
        _persist_request(db_url, request_id)
        mock_llm.configure('{"summary": "Requête terminée.", "findings": []}')

        delivery = asyncio.run(
            PipelineRunner().run(
                request_id, {"objective": OBJECTIVE, "request_type": "research"}
            )
        )
        assert delivery["status"], "le run doit aboutir"

        row = asyncio.run(_progress_row(db_url, request_id))
        checkpoint = asyncio.run(_checkpoint(db_url, request_id))

        assert row is not None and checkpoint is not None
        assert checkpoint["resumable"] is False, "un run abouti n'est pas reprise"
        assert row["current_step"] == "DELIVERY", (
            "un run terminé annonce sa livraison, pas une étape en cours"
        )
        assert row["steps_done"] == row["steps_total"], (
            "toutes les étapes du plan sont faites quand le run aboutit"
        )

        pipeline_runner.reset_state()
        response = client.get(f"/v1/requests/{request_id}/progress")
        assert response.status_code == 200
        assert response.json()["current_step"] == "DELIVERY"

    def test_a_request_without_progress_reports_the_initial_state(
        self, _fresh_engine: str
    ) -> None:
        """Une requête connue mais jamais exécutée n'invente aucun avancement."""
        db_url = _fresh_engine
        request_id = ULID.new("REQ_")
        _persist_request(db_url, request_id)

        response = client.get(f"/v1/requests/{request_id}/progress")

        assert response.status_code == 200
        body = response.json()
        assert body["steps_done"] == 0
        assert body["current_step"] == "RECEIVING"
        assert body["partial_findings_available"] is False

    def test_an_unknown_request_is_still_a_404(self, _fresh_engine: str) -> None:
        """Le contrat ne change pas : une requête inconnue reste 404."""
        response = client.get(f"/v1/requests/{ULID.new('REQ_')}/progress")
        assert response.status_code == 404