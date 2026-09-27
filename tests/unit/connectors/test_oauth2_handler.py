"""Unit tests for the OAuth2 bearer handler and its refresh flow (§41.4)."""

import pytest

from app.connectors.api.auth.oauth2_handler import OAuth2Handler
from app.core.errors import InfrastructureError


@pytest.mark.asyncio
async def test_refresh_exchanges_the_refresh_token() -> None:
    calls: list[str] = []

    async def fetch(refresh_token: str) -> dict:
        calls.append(refresh_token)
        return {"access_token": "AT-2", "expires_in": 3600}

    handler = OAuth2Handler(token="AT-1", refresh_token="RT-1", fetch_token=fetch)
    assert await handler.refresh() == "AT-2"
    assert calls == ["RT-1"]
    headers, _ = handler.apply()
    assert headers["Authorization"] == "Bearer AT-2"
    assert handler.token_expiry() is not None
    assert handler.token_expiry().endswith("Z")


@pytest.mark.asyncio
async def test_refresh_rotates_the_refresh_token_when_provided() -> None:
    async def fetch(_: str) -> dict:
        return {"access_token": "AT-2", "refresh_token": "RT-2"}

    handler = OAuth2Handler(token="AT-1", refresh_token="RT-1", fetch_token=fetch)
    await handler.refresh()
    # The rotated refresh token is used on the next call.
    seen: list[str] = []

    async def fetch2(token: str) -> dict:
        seen.append(token)
        return {"access_token": "AT-3"}

    handler.set_token_fetcher(fetch2)
    await handler.refresh()
    assert seen == ["RT-2"]


@pytest.mark.asyncio
async def test_refresh_without_refresh_token_fails_explicitly() -> None:
    with pytest.raises(InfrastructureError, match="requires a refresh token"):
        await OAuth2Handler(token="AT-1").refresh()


@pytest.mark.asyncio
async def test_refresh_without_token_fetcher_fails_explicitly() -> None:
    with pytest.raises(InfrastructureError, match="token fetcher"):
        await OAuth2Handler(token="AT-1", refresh_token="RT-1").refresh()


@pytest.mark.asyncio
async def test_refresh_wraps_transport_errors() -> None:
    async def boom(_: str) -> dict:
        raise RuntimeError("network down")

    with pytest.raises(InfrastructureError, match="token refresh failed"):
        await OAuth2Handler(token="AT-1", refresh_token="RT", fetch_token=boom).refresh()


@pytest.mark.asyncio
async def test_refresh_rejects_payload_without_access_token() -> None:
    async def fetch(_: str) -> dict:
        return {"token_type": "bearer"}

    with pytest.raises(InfrastructureError, match="no access_token"):
        await OAuth2Handler(token="AT-1", refresh_token="RT", fetch_token=fetch).refresh()


def test_set_token_rejects_empty_value() -> None:
    with pytest.raises(ValueError):
        OAuth2Handler().set_token("")


def test_set_refresh_token_rejects_empty_value() -> None:
    with pytest.raises(ValueError):
        OAuth2Handler().set_refresh_token("")


def test_apply_requires_a_token() -> None:
    with pytest.raises(InfrastructureError, match="no bearer token"):
        OAuth2Handler().apply()


def test_apply_copies_and_injects_the_header() -> None:
    headers = {"X-Trace": "1"}
    new_headers, params = OAuth2Handler(token="AT-1").apply(headers, {"q": "x"})
    assert new_headers == {"X-Trace": "1", "Authorization": "Bearer AT-1"}
    assert headers == {"X-Trace": "1"}  # input untouched
    assert params == {"q": "x"}


def test_expiry_is_false_without_an_expiry() -> None:
    assert OAuth2Handler(token="AT-1").is_expired() is False


def test_expiry_uses_the_declared_instant() -> None:
    from datetime import UTC, datetime, timedelta

    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    future = (now + timedelta(hours=1)).isoformat().replace("+00:00", "Z")
    past = (now - timedelta(hours=1)).isoformat().replace("+00:00", "Z")
    assert OAuth2Handler(token="T", expires_at=future).is_expired(now) is False
    assert OAuth2Handler(token="T", expires_at=past).is_expired(now) is True


def test_safe_state_never_exposes_the_token() -> None:
    handler = OAuth2Handler(token="AT-SECRET", refresh_token="RT-SECRET", token_url="https://x/t")
    state = handler.safe_state()
    assert "AT-SECRET" not in str(state)
    assert "RT-SECRET" not in str(state)
    assert state["has_access_token"] is True
    assert state["has_refresh_token"] is True
