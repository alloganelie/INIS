"""Tests for authorization persistence on accounts and sessions (B4-ter-2/3).

Acceptance criteria:
- test_account_role_scopes_persisted_to_db
- test_account_role_survives_new_session
- test_account_update_persists_role_and_scopes
- test_sessions_updated_at_changes_on_revoke
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
async def test_account_role_scopes_persisted_to_db(
    db_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """B4-ter-2: a role=reader account is stored with that role in PostgreSQL."""
    monkeypatch.setenv("INIS_DATABASE_URL", db_url)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as ac:
        res = await ac.post(
            "/v1/accounts",
            json={
                "username": "reader_b4ter",
                "email": "reader_b4ter@example.com",
                "password": "Password1!",
                "role": "reader",
                "scopes": ["read"],
            },
        )
    assert res.status_code == 201
    account_id = res.json()["id"]

    engine = create_engine(db_url)
    try:
        async with engine.connect() as conn:
            row = (
                await conn.execute(
                    text("SELECT role, scopes FROM accounts WHERE account_id = :id"),
                    {"id": account_id},
                )
            ).mappings().first()
    finally:
        await engine.dispose()

    assert row is not None
    assert row["role"] == "reader"
    assert list(row["scopes"]) == ["read"]


@pytest.mark.asyncio
async def test_account_role_survives_new_session(
    db_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """B4-ter-2: after dropping every in-memory store, the role is still read."""
    monkeypatch.setenv("INIS_DATABASE_URL", db_url)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as ac:
        created = await ac.post(
            "/v1/accounts",
            json={
                "username": "restart_user",
                "email": "restart@example.com",
                "password": "Password1!",
                "role": "reader",
                "scopes": ["read"],
            },
        )
    account_id = created.json()["id"]

    # Simulate a restart: no in-memory account, no cached session maker.
    reset_accounts_store()
    reset_session_maker()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as ac:
        fetched = await ac.get(f"/v1/accounts/{account_id}")

    assert fetched.status_code == 200
    body = fetched.json()
    assert body["role"] == "reader", "role must not fall back to 'operator'"
    assert body["scopes"] == ["read"]


@pytest.mark.asyncio
async def test_account_update_persists_role_and_scopes(
    db_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """B4-ter-2: PATCH role/scopes is written to the accounts table."""
    monkeypatch.setenv("INIS_DATABASE_URL", db_url)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as ac:
        created = await ac.post(
            "/v1/accounts",
            json={
                "username": "promote_user",
                "email": "promote@example.com",
                "password": "Password1!",
            },
        )
        account_id = created.json()["id"]
        patched = await ac.patch(
            f"/v1/accounts/{account_id}",
            json={"role": "admin", "scopes": ["admin", "read", "write"]},
        )

    assert patched.status_code == 200
    assert patched.json()["role"] == "admin"

    engine = create_engine(db_url)
    try:
        async with engine.connect() as conn:
            row = (
                await conn.execute(
                    text("SELECT role, scopes FROM accounts WHERE account_id = :id"),
                    {"id": account_id},
                )
            ).mappings().first()
    finally:
        await engine.dispose()

    assert row["role"] == "admin"
    assert list(row["scopes"]) == ["admin", "read", "write"]
