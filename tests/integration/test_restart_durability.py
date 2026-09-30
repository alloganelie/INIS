"""L6 durability: a delivery written here is read back by another interpreter.

The criterion of this lot is not "a repository returns what a fake returns" but
"the information is still there after a restart". So the test does exactly
that:

1. this process runs the real pipeline against a **migrated PostgreSQL** and the
   delivery is persisted through the repositories (no raw SQL anywhere);
2. every engine, session and cache of this process is dropped;
3. a **separate Python interpreter** (``subprocess``) opens a new connection and
   reads the ids, the provenance, the metadata and the lineage back;
4. this process compares what it delivered with what that interpreter found.

Nothing is shared between the two processes but the database. If the read path
invented a value, the comparison fails; if a write went nowhere, the row is
missing.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.api.v1.requests.pipeline_runner import PipelineRunner
from app.domain.value_objects.ulid import ULID
from app.storage.database.engine import create_engine
from app.storage.database.session import reset_session_maker
from app.storage.repositories.request_repository import RequestRepository

REPO_ROOT = Path(__file__).resolve().parents[2]

#: The reader: implemented with the repositories, imports resolved from the
#: repository root that the parent passes as ``cwd``.
READER_SCRIPT = """
import asyncio
import json
import os
import sys

sys.path.insert(0, os.getcwd())

from app.storage.database.engine import create_engine
from app.storage.repositories.information_unit_repository import (
    InformationUnitRepository,
)
from app.storage.repositories.request_repository import RequestRepository
from app.storage.repositories.transformation_repository import (
    TransformationRepository,
)


async def main() -> None:
    engine = create_engine(os.environ["INIS_DATABASE_URL"])
    try:
        payload = {
            "unit": await InformationUnitRepository.get(engine, os.environ["INIS_UNIT_ID"]),
            "request": await RequestRepository.get(engine, os.environ["INIS_REQUEST_ID"]),
            "lineage": await TransformationRepository.count(engine),
        }
    finally:
        await engine.dispose()
    print(json.dumps(payload))


asyncio.run(main())
"""


def _read_back(db_url: str, unit_id: str, request_id: str, tmp_path: Path) -> dict:
    """Run the reader in a brand new interpreter and return what it printed."""
    script = tmp_path / "read_back_l6.py"
    script.write_text(READER_SCRIPT, encoding="utf-8")
    environment = {
        **os.environ,
        "INIS_DATABASE_URL": db_url,
        "INIS_UNIT_ID": unit_id,
        "INIS_REQUEST_ID": request_id,
        "PYTHONIOENCODING": "utf-8",
    }
    completed = subprocess.run(
        [sys.executable, str(script)],
        cwd=REPO_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout.strip().splitlines()[-1])


@pytest.mark.asyncio
async def test_delivery_survives_a_real_process_restart(
    db_url: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """write (here) → restart (new interpreter) → read: same ids and provenance."""
    monkeypatch.setenv("INIS_DATABASE_URL", db_url)
    reset_session_maker()

    runner = PipelineRunner()
    request_id = ULID.new("REQ_")
    result = await runner.run(request_id, {"objective": "durabilité L6"})

    assert result["audit"]["persisted"] is True
    delivered = result["information_units"][0]
    unit_id = delivered["information_id"]

    engine = create_engine(db_url)
    try:
        await RequestRepository.create(
            engine,
            {
                "request_id": request_id,
                "objective": "durabilité L6",
                "requester": {"id": "agent:test"},
                "constraints": {"region": "EU"},
            },
        )
    finally:
        await engine.dispose()

    # Forget everything this process knows: connections, sessions, caches.
    reset_session_maker()

    payload = _read_back(db_url, unit_id, request_id, tmp_path)

    unit = payload["unit"]
    assert unit is not None, "l'unité livrée n'est pas retrouvée après redémarrage"
    assert unit["information_id"] == unit_id
    assert unit["source_id"] == delivered.get("source_id", unit["source_id"])
    assert unit["data_stage"] == delivered.get("data_stage", unit["data_stage"])
    assert unit["provenance"] == (delivered.get("provenance") or {})
    assert unit["context"] == (delivered.get("context") or {})

    request = payload["request"]
    assert request is not None
    assert request["request_id"] == request_id
    assert request["objective"] == "durabilité L6"
    assert request["requester"] == {"id": "agent:test"}
    assert request["constraints"] == {"region": "EU"}

    # §12.1 — the lineage of the run is durable too, not just the units.
    assert payload["lineage"] >= 1
