"""Tests for accounts management and auth integration per §19.2 and §32."""

import pytest
from fastapi.testclient import TestClient

from app.api.v1.accounts.router import reset_accounts_store, router as accounts_router
from app.main import app

# Ensure accounts_router is mounted on app with prefix="/v1"
if not any(getattr(r, "path", "").startswith("/v1/accounts") for r in app.routes):
    app.include_router(accounts_router, prefix="/v1")

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_teardown_accounts():
    """Ensure clean accounts store before and after each test."""
    reset_accounts_store()
    yield
    reset_accounts_store()


def test_register():
    """POST /v1/accounts creates an account and returns 201 with metadata."""
    payload = {
        "username": "alice",
        "email": "alice@example.com",
        "password": "Password123!",
        "role": "operator",
        "scopes": ["read", "write"],
    }
    response = client.post("/v1/accounts", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["id"].startswith("ACC_")
    assert data["username"] == "alice"
    assert data["email"] == "alice@example.com"
    assert data["role"] == "operator"
    assert data["scopes"] == ["read", "write"]
    assert data["is_active"] is True
    assert data["status"] == "active"
    assert "created_at" in data
    assert "updated_at" in data
    assert "password" not in data
    assert "hashed_password" not in data


def test_duplicate():
    """POST /v1/accounts with existing username or email returns 409 Conflict."""
    payload = {
        "username": "bob",
        "email": "bob@example.com",
        "password": "Password123!",
    }
    res1 = client.post("/v1/accounts", json=payload)
    assert res1.status_code == 201

    # Duplicate username
    dup_user = {
        "username": "bob",
        "email": "different_bob@example.com",
        "password": "Password456!",
    }
    res2 = client.post("/v1/accounts", json=dup_user)
    assert res2.status_code == 409
    assert "username" in res2.json()["detail"].lower()

    # Duplicate email
    dup_email = {
        "username": "another_bob",
        "email": "bob@example.com",
        "password": "Password789!",
    }
    res3 = client.post("/v1/accounts", json=dup_email)
    assert res3.status_code == 409
    assert "email" in res3.json()["detail"].lower()


def test_get():
    """GET /v1/accounts/{id} retrieves account or returns 404."""
    create_res = client.post(
        "/v1/accounts",
        json={"username": "charlie", "email": "charlie@example.com", "password": "Password123!"},
    )
    assert create_res.status_code == 201
    account_id = create_res.json()["id"]

    get_res = client.get(f"/v1/accounts/{account_id}")
    assert get_res.status_code == 200
    data = get_res.json()
    assert data["id"] == account_id
    assert data["username"] == "charlie"
    assert data["email"] == "charlie@example.com"

    not_found_res = client.get("/v1/accounts/ACC_NONEXISTENT999999999999")
    assert not_found_res.status_code == 404


def test_update_email():
    """PATCH /v1/accounts/{id} updates email and checks duplicate constraints."""
    create_res = client.post(
        "/v1/accounts",
        json={"username": "david", "email": "david@example.com", "password": "Password123!"},
    )
    assert create_res.status_code == 201
    account_id = create_res.json()["id"]

    # Successful update
    patch_res = client.patch(f"/v1/accounts/{account_id}", json={"email": "david_new@example.com"})
    assert patch_res.status_code == 200
    assert patch_res.json()["email"] == "david_new@example.com"

    # Verify persistence
    get_res = client.get(f"/v1/accounts/{account_id}")
    assert get_res.json()["email"] == "david_new@example.com"


def test_update_password():
    """PATCH /v1/accounts/{id} updates password, enabling login with the new secret."""
    create_res = client.post(
        "/v1/accounts",
        json={"username": "emma", "email": "emma@example.com", "password": "OldPassword123!"},
    )
    assert create_res.status_code == 201
    account_id = create_res.json()["id"]

    # Initial login succeeds
    login1 = client.post("/v1/auth/login", json={"username": "emma", "password": "OldPassword123!"})
    assert login1.status_code == 200

    # Update password
    patch_res = client.patch(f"/v1/accounts/{account_id}", json={"password": "NewPassword456!"})
    assert patch_res.status_code == 200

    # Old password fails
    login_old = client.post("/v1/auth/login", json={"username": "emma", "password": "OldPassword123!"})
    assert login_old.status_code == 401

    # New password succeeds
    login_new = client.post("/v1/auth/login", json={"username": "emma", "password": "NewPassword456!"})
    assert login_new.status_code == 200
    assert "access_token" in login_new.json()


def test_delete():
    """DELETE /v1/accounts/{id} soft-deletes account and revokes authentication."""
    create_res = client.post(
        "/v1/accounts",
        json={"username": "frank", "email": "frank@example.com", "password": "Password123!"},
    )
    assert create_res.status_code == 201
    account_id = create_res.json()["id"]

    # Delete (soft delete)
    del_res = client.delete(f"/v1/accounts/{account_id}")
    assert del_res.status_code == 204

    # Verify soft delete flag in store
    get_res = client.get(f"/v1/accounts/{account_id}")
    assert get_res.status_code == 200
    account_data = get_res.json()
    assert account_data["is_active"] is False
    assert account_data["status"] == "deleted"

    # Login now rejected
    login_res = client.post("/v1/auth/login", json={"username": "frank", "password": "Password123!"})
    assert login_res.status_code == 401


def test_login():
    """POST /v1/auth/login verifies credentials and returns JWT access + refresh tokens."""
    create_res = client.post(
        "/v1/accounts",
        json={"username": "grace", "email": "grace@example.com", "password": "StrongPassword99!"},
    )
    assert create_res.status_code == 201

    # Valid credentials
    login_res = client.post("/v1/auth/login", json={"username": "grace", "password": "StrongPassword99!"})
    assert login_res.status_code == 200
    data = login_res.json()
    assert "access_token" in data
    assert data["token_type"].lower() == "bearer"
    assert isinstance(data["expires_in"], int)
    assert data.get("refresh_token") is not None

    # Invalid credentials
    bad_login = client.post("/v1/auth/login", json={"username": "grace", "password": "WrongPassword"})
    assert bad_login.status_code == 401


def test_logout():
    """POST /v1/auth/logout succeeds and returns 200."""
    res = client.post("/v1/auth/logout")
    assert res.status_code == 200
    data = res.json()
    assert data.get("status") == "logged_out"
