"""Tests for authentication middleware and endpoints per §19 and §32."""

import pytest
from fastapi.testclient import TestClient

from app.api.middleware.auth_middleware import set_security_validator, set_strict_auth_mode
from app.main import app

client = TestClient(app)


def test_login_ok() -> None:
    """POST /v1/auth/login with valid credentials returns 200 with JWT access token."""
    res = client.post("/v1/auth/login", json={"username": "admin", "password": "adminpassword"})
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert data["token_type"].lower() == "bearer"
    assert isinstance(data["expires_in"], int)
    assert data.get("refresh_token") is not None


def test_login_ko() -> None:
    """POST /v1/auth/login with invalid credentials returns 401."""
    res = client.post("/v1/auth/login", json={"username": "wrong_user", "password": "wrong_password"})
    assert res.status_code == 401
    assert "detail" in res.json()


def test_refresh() -> None:
    """POST /v1/auth/refresh with valid refresh token returns 200 with new access token."""
    login_res = client.post("/v1/auth/login", json={"username": "admin", "password": "adminpassword"})
    assert login_res.status_code == 200
    refresh_token = login_res.json()["refresh_token"]

    ref_res = client.post("/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert ref_res.status_code == 200
    data = ref_res.json()
    assert "access_token" in data
    assert data["token_type"].lower() == "bearer"


def test_me_without_token() -> None:
    """GET /v1/auth/me without token returns 401 in strict auth mode."""
    try:
        set_strict_auth_mode(True)
        res = client.get("/v1/auth/me")
        assert res.status_code == 401
    finally:
        set_strict_auth_mode(None)


def test_me_with_token() -> None:
    """GET /v1/auth/me with valid Bearer token returns 200 with actor_id and scopes."""
    login_res = client.post("/v1/auth/login", json={"username": "admin", "password": "adminpassword"})
    assert login_res.status_code == 200
    access_token = login_res.json()["access_token"]

    try:
        set_strict_auth_mode(True)
        res = client.get("/v1/auth/me", headers={"Authorization": f"Bearer {access_token}"})
        assert res.status_code == 200
        data = res.json()
        assert data["actor_id"] == "ACT_01ARZ3NDEKTSV4RRFFQ69G5F01"
        assert "admin" in data["scopes"]
        assert "read" in data["scopes"]
    finally:
        set_strict_auth_mode(None)


def test_me_with_invalid_token() -> None:
    """GET /v1/auth/me with an invalid token returns 401."""
    try:
        set_strict_auth_mode(True)
        res = client.get("/v1/auth/me", headers={"Authorization": "Bearer invalid.token.payload"})
        assert res.status_code == 401
    finally:
        set_strict_auth_mode(None)


def test_scope_insufficient_returns_403() -> None:
    """Request with insufficient scope returns 403."""
    login_res = client.post("/v1/auth/login", json={"username": "reader", "password": "readerpassword"})
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]

    try:
        set_strict_auth_mode(True)
        res = client.get(
            "/v1/auth/me",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Required-Scope": "admin",
            },
        )
        assert res.status_code == 403
        assert "detail" in res.json()
    finally:
        set_strict_auth_mode(None)


def test_exempt_endpoints_accessible_without_token() -> None:
    """Public endpoints /health, /version, /v1/docs are accessible without credentials even in strict mode."""
    try:
        set_strict_auth_mode(True)
        assert client.get("/health").status_code == 200
        assert client.get("/version").status_code == 200
        assert client.get("/v1/openapi.json").status_code == 200
    finally:
        set_strict_auth_mode(None)


def test_api_key_authentication() -> None:
    """X-API-Key header authenticates and grants access to /v1/auth/me."""
    try:
        set_strict_auth_mode(True)
        res = client.get("/v1/auth/me", headers={"X-API-Key": "inis-admin-key"})
        assert res.status_code == 200
        data = res.json()
        assert data["actor_id"] == "api_key_actor"
    finally:
        set_strict_auth_mode(None)


def test_app_security_authn_validator_integration() -> None:
    """When a mock validator is provided via set_security_validator, it is called."""
    class MockValidator:
        def validate_jwt(self, token: str):
            if token == "mock_valid":
                return {"actor_id": "ACT_MOCK_USER", "scopes": ["mock_scope"]}
            return None

    try:
        set_strict_auth_mode(True)
        set_security_validator(MockValidator())
        res = client.get("/v1/auth/me", headers={"Authorization": "Bearer mock_valid"})
        assert res.status_code == 200
        assert res.json()["actor_id"] == "ACT_MOCK_USER"
        assert res.json()["scopes"] == ["mock_scope"]

        res_ko = client.get("/v1/auth/me", headers={"Authorization": "Bearer bad_mock"})
        assert res_ko.status_code == 401
    finally:
        set_security_validator(None)
        set_strict_auth_mode(None)

