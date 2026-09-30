"""§41.1 — une exécution interrompue **pour de bon** reprend sans rien perdre.

Le plan est explicite : « ne te contente pas d'un test qui appelle une fonction
deux fois ». Ici :

1. un **processus enfant** exécute le pipeline contre le vrai PostgreSQL et se
   fait **tuer net** (`os._exit`) pendant une étape d'acquisition — pas
   d'exception rattrapée, pas de nettoyage ;
2. le parent relit l'état **persistant** laissé derrière (point de reprise) ;
3. un nouveau runner **reprend** : les étapes déjà validées sont **rejouées**
   depuis le point de reprise (elles ne sont pas ré-exécutées) et les
   informations acquises avant l'interruption sont **livrées** ;
4. après reprise, le point de reprise n'est plus « resumable » (état persistant
   à jour) et la provenance dit d'où l'on vient.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, ClassVar
from unittest.mock import AsyncMock

import pytest

from app.api.v1.requests.pipeline_runner import PipelineRunner
from app.domain.value_objects.ulid import ULID
from app.storage.database.engine import create_engine, set_default_engine
from app.storage.database.session import reset_session_maker
from app.storage.repositories.checkpoint_repository import CheckpointRepository
from app.storage.repositories.information_unit_repository import (
    InformationUnitRepository,
)
from app.storage.repositories.request_repository import RequestRepository

REPO_ROOT = Path(__file__).resolve().parents[2]
OBJECTIVE = "Quelle est la population de Paris et celle de Lyon ?"

#: The child: same pipeline, same database, killed during its second step.
CHILD_SCRIPT = """
import asyncio
import json
import os
import sys

sys.path.insert(0, os.getcwd())

from app.api.v1.requests.pipeline_runner import PipelineRunner
from app.storage.database.engine import set_default_engine
from app.storage.database.session import reset_session_maker

KILL_CODE = 137  # SIGKILL, as a supervisor would report it


async def _kill_during_acquisition(*args, **kwargs):
    \"\"\"Kept for readability: the kill now happens through the checkpoint hook.\"\"\"
    os._exit(KILL_CODE)


async def main() -> None:
    os.environ["INIS_NULL_POOL"] = "1"
    set_default_engine(None)
    reset_session_maker()

    from app.api.v1.requests.pipeline_runner import PipelineRunner

    original_checkpoint = PipelineRunner._checkpoint_step

    async def _commit_then_die(self, request_id, **kwargs):
        \"\"\"Write the real checkpoint, then die: interruption mid-execution.\"\"\"
        await original_checkpoint(self, request_id, **kwargs)
        if kwargs.get("step_index", 0) >= 1:
            os._exit(KILL_CODE)

    PipelineRunner._checkpoint_step = _commit_then_die

    payload = json.loads(os.environ["INIS_REQUEST_PAYLOAD"])
    print("CHILD_RUNNING", flush=True)
    await PipelineRunner().run(os.environ["INIS_REQUEST_ID"], payload)
    print("NOT_KILLED")


try:
    asyncio.run(main())
except BaseException as error:  # noqa: BLE001 - the parent needs to see why
    import traceback

    print("CHILD_FAILED:", type(error).__name__, error, flush=True)
    traceback.print_exc()
"""


@pytest.fixture(autouse=True)
def _fresh_engine(db_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Bind this process to the test database, in the current event loop."""
    monkeypatch.setenv("INIS_DATABASE_URL", db_url)
    monkeypatch.setenv("INIS_NULL_POOL", "1")
    set_default_engine(None)
    reset_session_maker()
    yield
    set_default_engine(None)
    reset_session_maker()


@pytest.fixture
def no_web(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """The resumed run may acquire: the provider answers, and is observable."""
    search = AsyncMock(return_value=[])
    monkeypatch.setattr("app.connectors.web.provider_router.ProviderRouter.search", search)
    monkeypatch.setattr(
        "app.connectors.web.extractors.wikipedia_extractor.WikipediaExtractor.extract",
        AsyncMock(return_value={}),
    )
    return search


def _kill_mid_run(db_url: str, request_id: str, payload: dict[str, Any], tmp_path: Path) -> str:
    """Run the pipeline in a child process and kill it during acquisition."""
    script = tmp_path / "interrupted_run.py"
    script.write_text(CHILD_SCRIPT, encoding="utf-8")
    completed = subprocess.run(
        [sys.executable, str(script)],
        cwd=REPO_ROOT,
        env={
            **os.environ,
            "INIS_DATABASE_URL": db_url,
            "INIS_REQUEST_ID": request_id,
            "INIS_REQUEST_PAYLOAD": json.dumps(payload),
            "PYTHONIOENCODING": "utf-8",
        },
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    return completed.stdout + completed.stderr


async def _checkpoint(db_url: str, request_id: str) -> dict[str, Any] | None:
    engine = create_engine(db_url)
    try:
        return await CheckpointRepository.get(engine, request_id)
    finally:
        await engine.dispose()


class TestTheInterruptedRunLeavesAResumableState:
    """L'interruption laisse un état persistant, pas une ardoise vide."""

    @pytest.mark.asyncio
    async def test_the_checkpoint_survives_the_kill(
        self, db_url: str, tmp_path: Path
    ) -> None:
        request_id = ULID.new("REQ_")
        payload = {"objective": OBJECTIVE, "request_type": "research"}

        output = _kill_mid_run(db_url, request_id, payload, tmp_path)
        assert "NOT_KILLED" not in output, (
            f"le processus enfant aurait dû être tué pendant l'acquisition : {output[-400:]}"
        )

        checkpoint = await _checkpoint(db_url, request_id)

        assert checkpoint is not None, (
            f"l'interruption ne laisse aucun point de reprise — sortie de l'enfant : {output[-900:]}"
        )
        assert checkpoint["resumable"] is True
        assert checkpoint["step_index"] >= 1
        assert checkpoint["payload"], "les étapes validées doivent être persistées"
        assert checkpoint["last_committed_step"]


class TestTheResumeContinuesWithoutLosingAnything:
    """La reprise rejoue le préfixe validé et livre ce qui a été acquis."""

    async def _interrupt(self, db_url: str, tmp_path: Path) -> tuple[str, dict[str, Any]]:
        """Kill a run mid-execution and return the request and its payload."""
        request_id = ULID.new("REQ_")
        payload = {"objective": OBJECTIVE, "request_type": "research"}
        output = _kill_mid_run(db_url, request_id, payload, tmp_path)
        state = await _checkpoint(db_url, request_id)
        assert state is not None and state["resumable"] is True and state["payload"], (
            f"interruption manquée — sortie de l'enfant : {output[-600:]} ; état = {state}"
        )
        return request_id, payload

    @pytest.mark.asyncio
    async def test_the_committed_prefix_is_not_executed_again(
        self, db_url: str, tmp_path: Path, no_web: AsyncMock, mock_llm: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """§41.1 — « ne pas refaire » se prouve : la mémoire n'est pas rappelée."""
        request_id, payload = await self._interrupt(db_url, tmp_path)
        checkpoint = await _checkpoint(db_url, request_id)
        assert checkpoint is not None

        calls: list[str] = []

        class _RecordingSearch:
            """Le premier pas (memory_lookup) est rejoué : il ne doit pas partir."""

            mode = "hybrid"
            limitations: ClassVar[list[str]] = []
            units: ClassVar[dict[str, Any]] = {}

            async def __call__(self, question: str, requirements: Any) -> list[Any]:
                calls.append(question)
                return []

        import app.api.v1.requests.pipeline_runner as runner_module

        monkeypatch.setattr(runner_module, "HybridMemorySearch", lambda **kwargs: _RecordingSearch())
        delivery = await PipelineRunner().resume_interrupted(request_id, payload)

        assert delivery is not None, (
            f"la reprise doit aboutir ; point de reprise = {checkpoint}"
        )
        assert calls == [], "l'étape déjà validée ne doit pas être ré-exécutée"
        resumed = delivery["provenance"]["resumed_from"]
        assert resumed["step_index"] == checkpoint["step_index"]
        assert resumed["replayed_steps"] == checkpoint["step_index"]
        assert any("Reprise §41.1" in item for item in delivery["limitations"])

    @pytest.mark.asyncio
    async def test_the_resumed_run_is_complete_and_not_duplicated(
        self, db_url: str, tmp_path: Path, no_web: AsyncMock, mock_llm: Any, monkeypatch
    ) -> None:
        """Les informations acquises sont livrées, une fois."""
        request_id, payload = await self._interrupt(db_url, tmp_path)

        # Le payload n'est pas fourni : il est relu depuis la table `requests`.
        engine = create_engine(db_url)
        try:
            await RequestRepository.create(
                engine,
                {
                    "request_id": request_id,
                    "request_type": "research",
                    "objective": OBJECTIVE,
                    "payload": payload,
                },
            )
        finally:
            await engine.dispose()

        delivery = await PipelineRunner().resume_interrupted(request_id)

        assert delivery is not None
        assert delivery["status"] != "failed"
        identifiers = [unit["information_id"] for unit in delivery["information_units"]]
        assert identifiers, "le colis repris ne peut pas être vide"
        assert len(identifiers) == len(set(identifiers)), "aucune unité en double"

        # Aucune duplication en base non plus : une unité livrée = une ligne.
        engine = create_engine(db_url)
        try:
            stored = await InformationUnitRepository.list_for_request(engine, request_id)
        finally:
            await engine.dispose()
        stored_ids = [unit["information_id"] for unit in stored]
        assert len(stored_ids) == len(set(stored_ids))

    @pytest.mark.asyncio
    async def test_the_checkpoint_is_closed_after_the_resume(
        self, db_url: str, tmp_path: Path, no_web: AsyncMock, mock_llm: Any
    ) -> None:
        """L'état persistant suit : un run repris et terminé n'est plus reprenable."""
        request_id, payload = await self._interrupt(db_url, tmp_path)
        state = await _checkpoint(db_url, request_id)
        delivery = await PipelineRunner().resume_interrupted(request_id, payload)
        assert delivery is not None, f"première reprise refusée ; point de reprise = {state}"

        checkpoint = await _checkpoint(db_url, request_id)
        assert checkpoint is not None
        assert checkpoint["resumable"] is False
        assert await PipelineRunner().resume_interrupted(request_id, payload) is None, (
            "un run terminé ne se reprend pas deux fois"
        )
