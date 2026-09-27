"""Tests for real database persistence of accounts and sessions per §19.2.

Acceptance criteria of B4-bis Constat 2:
- test_accounts_persists_to_db_with_url: create account -> SELECT accounts -> present
- test_accounts_fallback_in_memory_only_without_url
- test_session_persisted_on_login
- test_session_revoked_on_logout
"""

from __future__ import annotations

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
async def test_accounts_fallback_in_memory_only_without_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without INIS_DATABASE_URL, accounts only live in the in-memory store."""
    monkeypatch.delenv("INIS_DATABASE_URL", raising=False)
    payload = {
        "username": "offline_user",
        "email": "offline@example.com",
        "password": "Password123!",
    }
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.post("/v1/accounts", json=payload)
    assert res.status_code == 201
    assert res.json()["username"] == "offline_user"


@pytest.mark.asyncio
async def test_accounts_persists_to_db_with_url(db_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """With INIS_DATABASE_URL, POST /v1/accounts writes a real row into accounts."""
    monkeypatch.setenv("INIS_DATABASE_URL", db_url)
    payload = {
        "username": "db_user",
        "email": "db_user@example.com",
        "password": "Password123!",
    }
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.post("/v1/accounts", json=payload)
    assert res.status_code == 201
    account_id = res.json()["id"]

    engine = create_engine(db_url)
    try:
        async with engine.connect() as conn:
            row = (
                await conn.execute(
                    text("SELECT account_id, username, email, status FROM accounts WHERE account_id = :id"),
                    {"id": account_id},
                )
            ).mappings().first()
    finally:
        await engine.dispose()

    assert row is not None
    assert row["account_id"] == account_id
    assert row["username"] == "db_user"
    assert row["email"] == "db_user@example.com"
    assert row["status"] == "active"


@pytest.mark.asyncio
async def test_session_persisted_on_login(db_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """When a real account logs in, a session row is inserted in sessions table."""
    monkeypatch.setenv("INIS_DATABASE_URL", db_url)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as ac:
        reg = await ac.post(
            "/v1/accounts",
            json={"username": "session_user", "email": "session@example.com", "password": "SecretPassword1!"},
        )
        assert reg.status_code == 201
        account_id = reg.json()["id"]

        login_res = await ac.post(
            "/v1/auth/login",
            json={"username": "session_user", "password": "SecretPassword1!"},
        )
        assert login_res.status_code == 200
        token = login_res.json()["access_token"]
        assert token

    engine = create_engine(db_url)
    try:
        async with engine.connect() as conn:
            row = (
                await conn.execute(
                    text("SELECT session_id, account_id, revoked_at FROM sessions WHERE account_id = :id"),
                    {"id": account_id},
                )
            ).mappings().first()
    finally:
        await engine.dispose()

    assert row is not None
    assert row["account_id"] == account_id
    assert row["revoked_at"] is None


@pytest.mark.asyncio
async def test_session_revoked_on_logout(db_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """POST /v1/auth/logout sets revoked_at on the persisted session row."""
    monkeypatch.setenv("INIS_DATABASE_URL", db_url)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as ac:
        reg = await ac.post(
            "/v1/accounts",
            json={"username": "logout_user", "email": "logout@example.com", "password": "SecretPassword1!"},
        )
        assert reg.status_code == 201
        account_id = reg.json()["id"]

        login_res = await ac.post(
            "/v1/auth/login",
            json={"username": "logout_user", "password": "SecretPassword1!"},
        )
        token = login_res.json()["access_token"]

        logout_res = await ac.post("/v1/auth/logout", headers={"Authorization": f"Bearer {token}"})
        assert logout_res.status_code == 200

    engine = create_engine(db_url)
    try:
        async with engine.connect() as conn:
            row = (
                await conn.execute(
                    text("SELECT session_id, revoked_at FROM sessions WHERE account_id = :id"),
                    {"id": account_id},
                )
            ).mappings().first()
    finally:
        await engine.dispose()

    assert row is not None
    assert row["revoked_at"] is not None
