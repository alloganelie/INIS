"""Test for sessions.updated_at (B4-ter-3, §19.2).

Acceptance criteria: test_sessions_updated_at_changes_on_revoke - login, wait, logout,
then SELECT sessions and compare updated_at with created_at.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest
from sqlalchemy import text

from app.api.v1.accounts.router import reset_accounts_store
from app.main import app
from app.storage.database.engine import create_engine
from app.storage.database.session import reset_session_maker


@pytest.fixture(autouse=True)
def _clean_stores(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("INIS_NULL_POOL", "true")
    reset_accounts_store()
    reset_session_maker()
    yield
    reset_accounts_store()
    reset_session_maker()


@pytest.mark.asyncio
async def test_sessions_updated_at_changes_on_revoke(
    db_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """B4-ter-3: sessions.updated_at exists and moves when the session is revoked."""
    monkeypatch.setenv("INIS_DATABASE_URL", db_url)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as ac:
        created = await ac.post(
            "/v1/accounts",
            json={
                "username": "revoke_user",
                "email": "revoke@example.com",
                "password": "Password1!",
            },
        )
        account_id = created.json()["id"]
        login = await ac.post(
            "/v1/auth/login",
            json={"username": "revoke_user", "password": "Password1!"},
        )
        token = login.json()["access_token"]

        engine = create_engine(db_url)
        try:
            async with engine.connect() as conn:
                before = (
                    await conn.execute(
                        text(
                            "SELECT created_at, updated_at FROM sessions "
                            "WHERE account_id = :id"
                        ),
                        {"id": account_id},
                    )
                ).mappings().first()
            assert before is not None
            assert before["updated_at"] is not None, "sessions.updated_at must be filled"

            await asyncio.sleep(1.1)
            logout = await ac.post(
                "/v1/auth/logout", headers={"Authorization": f"Bearer {token}"}
            )
            assert logout.status_code == 200

            async with engine.connect() as conn:
                after = (
                    await conn.execute(
                        text(
                            "SELECT created_at, updated_at, revoked_at FROM sessions "
                            "WHERE account_id = :id"
                        ),
                        {"id": account_id},
                    )
                ).mappings().first()
        finally:
            await engine.dispose()

    assert after is not None
    assert after["revoked_at"] is not None
    assert after["updated_at"] > after["created_at"]
