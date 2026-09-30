"""L6.4 — an Information Request must be readable after a restart.

The API kept requests in ``_REQUESTS_STORE`` (a module-level dict): a restart, a
rebuild or a second worker erased the history. The §7 request is now written to
the ``requests`` table (revision 0007) and read back from it.

The restart is simulated by emptying exactly what a restart empties: the
in-process dict, the runner state, the session maker and the cached engine. The
read then has to come from PostgreSQL — and the fields the table does not carry
are asserted to stay empty, because inventing them would be worse than losing
them (§37: signaler > inventer).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.v1.requests.pipeline_runner import pipeline_runner
from app.api.v1.requests.router import _REQUESTS_STORE
from app.storage.database.engine import set_default_engine
from app.storage.database.session import reset_session_maker


def _simulate_restart() -> None:
    """Drop every in-process trace of the previous run."""
    _REQUESTS_STORE.clear()
    pipeline_runner.reset_state()
    reset_session_maker()
    set_default_engine(None)


def test_request_is_readable_after_a_restart(db_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """A request created before the restart comes back **whole** after it.

    Since revision ``0016`` the row carries the §7 payload: the question, the
    context, the required information and the budget must be the ones that were
    asked, not defaults (§7).
    """
    monkeypatch.setenv("INIS_DATABASE_URL", db_url)
    reset_session_maker()
    set_default_engine(None)

    from app.main import app

    asked = {
        "objective": "durabilité des demandes (L6.4)",
        "request_type": "research",
        "question": "Quelle est la population de Paris en 2024 ?",
        "context": {"langue": "fr", "niveau": "détaillé"},
        "required_information": ["population", "année"],
        "requester": {"id": "agent:test"},
        "permissions": {"scope": "public"},
        "budget": {"max_total_cost_usd": 1.5, "max_web_requests": 12},
    }
    with TestClient(app) as client:
        created = client.post("/v1/requests", json=asked)
        assert created.status_code == 201, created.text
        request_id = created.json()["request_id"]

    _simulate_restart()

    with TestClient(app) as restarted:
        fetched = restarted.get(f"/v1/requests/{request_id}")

    assert fetched.status_code == 200, fetched.text
    payload = fetched.json()
    assert payload["request_id"] == request_id
    assert payload["objective"] == asked["objective"]
    assert payload["requester"] == {"id": "agent:test"}
    assert payload["created_at"] is not None
    assert payload["status"]
    # §7 — the whole request survived, not only the durable columns.
    assert payload["question"] == asked["question"]
    assert payload["context"] == asked["context"]
    assert payload["required_information"] == asked["required_information"]
    assert payload["permissions"] == asked["permissions"]
    assert payload["budget"]["max_total_cost_usd"] == 1.5
    # The live pipeline state is process-local by nature: a restored request
    # reports ``None`` rather than a state nobody observed.
    assert payload["pipeline_state"] is None


def test_a_row_without_payload_falls_back_to_the_columns(
    db_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A row written before revision 0016 is served from its columns, not invented.

    The repository is called directly without a ``payload``: that is exactly the
    shape of a row created by an older version. The durable subset comes back
    and the §7 fields the table never carried stay empty — stated, not faked.
    """
    import asyncio

    from app.main import app
    from app.storage.database.engine import create_engine
    from app.storage.repositories.request_repository import RequestRepository

    monkeypatch.setenv("INIS_DATABASE_URL", db_url)
    reset_session_maker()
    set_default_engine(None)

    request_id = "REQ_0016_LEGACY_ROW"
    engine = create_engine(db_url)
    try:
        asyncio.run(
            RequestRepository.create(
                engine,
                {
                    "request_id": request_id,
                    "request_type": "research",
                    "objective": "ligne antérieure à 0016",
                    "requester": {"id": "agent:legacy"},
                },
            )
        )
    finally:
        asyncio.run(engine.dispose())

    _simulate_restart()

    with TestClient(app) as restarted:
        fetched = restarted.get(f"/v1/requests/{request_id}")

    assert fetched.status_code == 200, fetched.text
    payload = fetched.json()
    assert payload["objective"] == "ligne antérieure à 0016"
    assert payload["requester"] == {"id": "agent:legacy"}
    assert payload["question"] is None
    assert payload["context"] == {}


def test_unknown_request_is_still_a_404(db_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """The durable lookup does not turn an unknown id into a success."""
    monkeypatch.setenv("INIS_DATABASE_URL", db_url)
    reset_session_maker()
    set_default_engine(None)

    from app.main import app

    _simulate_restart()
    with TestClient(app) as client:
        fetched = client.get("/v1/requests/REQ_000000000000000000000000ZZ")

    assert fetched.status_code == 404


def test_without_a_database_the_history_stays_volatile(monkeypatch: pytest.MonkeyPatch) -> None:
    """No PostgreSQL: the documented in-memory mode, with its limitation.

    This is the honest half of the plan item: without a database the history
    *is* volatile, and the test states it instead of pretending otherwise.
    """
    monkeypatch.delenv("INIS_DATABASE_URL", raising=False)
    reset_session_maker()
    set_default_engine(None)

    from app.main import app

    with TestClient(app) as client:
        created = client.post("/v1/requests", json={"objective": "sans base"})
        assert created.status_code == 201
        request_id = created.json()["request_id"]

    _simulate_restart()

    with TestClient(app) as client:
        assert client.get(f"/v1/requests/{request_id}").status_code == 404
