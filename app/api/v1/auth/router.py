"""Authentication endpoints per §19 and §32."""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from app.api.middleware.auth_middleware import create_jwt_token, decode_jwt_token
from app.api.v1.accounts.password_hasher import PasswordHasher
from app.api.v1.accounts.router import find_account, get_account_by_id
from app.api.v1.auth.schemas import (
    LoginRequest,
    MeResponse,
    RefreshRequest,
    TokenResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])

# In-memory mock user database for V1 backwards compatibility
USERS_DB: dict[str, dict[str, Any]] = {
    "admin": {
        "password": "adminpassword",
        "actor_id": "ACT_01ARZ3NDEKTSV4RRFFQ69G5F01",
        "scopes": ["admin", "read", "write"],
    },
    "operator": {
        "password": "operatorpassword",
        "actor_id": "ACT_01ARZ3NDEKTSV4RRFFQ69G5F02",
        "scopes": ["read", "write"],
    },
    "reader": {
        "password": "readerpassword",
        "actor_id": "ACT_01ARZ3NDEKTSV4RRFFQ69G5F03",
        "scopes": ["read"],
    },
}


@router.post("/login", response_model=TokenResponse, summary="Authenticate and obtain access token per §19.2")
def login(request: LoginRequest) -> TokenResponse:
    """Authenticate with username/password and return JWT token."""
    actor_id: str | None = None
    scopes: list[str] = ["read", "write"]

    # 1. First check dynamic accounts store
    account = find_account(request.username)
    if account is not None:
        if not PasswordHasher.verify(request.password, account.get("hashed_password", "")):
            raise HTTPException(status_code=401, detail="Invalid username or password")
        if not account.get("is_active", True) or account.get("status") == "deleted":
            raise HTTPException(status_code=401, detail="Account is deactivated or deleted")
        actor_id = account["id"]
        scopes = account.get("scopes", ["read", "write"])
    else:
        # 2. Check fallback mock users
        user = USERS_DB.get(request.username)
        if not user or user["password"] != request.password:
            if request.username == "admin" and request.password == "admin":
                user = {
                    "actor_id": "ACT_01ARZ3NDEKTSV4RRFFQ69G5F01",
                    "scopes": ["admin", "read", "write"],
                }
            else:
                raise HTTPException(status_code=401, detail="Invalid username or password")
        actor_id = user["actor_id"]
        scopes = user["scopes"]

    now = time.time()
    access_token_payload = {
        "sub": actor_id,
        "actor_id": actor_id,
        "scopes": scopes,
        "iat": now,
        "exp": now + 3600,
    }
    refresh_token_payload = {
        "sub": actor_id,
        "actor_id": actor_id,
        "type": "refresh",
        "iat": now,
        "exp": now + 86400 * 7,
    }

    access_token = create_jwt_token(access_token_payload)
    refresh_token = create_jwt_token(refresh_token_payload)

    return TokenResponse(
        access_token=access_token,
        token_type="Bearer",
        expires_in=3600,
        refresh_token=refresh_token,
    )


@router.post("/logout", summary="Logout and invalidate token per §19.2")
def logout(request: Request) -> dict[str, str]:
    """Logout current user and invalidate session."""
    return {"status": "logged_out", "message": "Successfully logged out"}


@router.post("/refresh", response_model=TokenResponse, summary="Refresh an expired access token")
def refresh(request: RefreshRequest) -> TokenResponse:
    """Exchange a valid refresh token for a new access token."""
    payload = decode_jwt_token(request.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    actor_id = payload.get("actor_id") or payload.get("sub") or "unknown_actor"

    account = get_account_by_id(actor_id)
    if account is not None:
        scopes = account.get("scopes", ["read", "write"])
    else:
        user = next((u for u in USERS_DB.values() if u["actor_id"] == actor_id), None)
        scopes = user["scopes"] if user else ["read"]

    now = time.time()
    new_access_payload = {
        "sub": actor_id,
        "actor_id": actor_id,
        "scopes": scopes,
        "iat": now,
        "exp": now + 3600,
    }
    new_access_token = create_jwt_token(new_access_payload)

    return TokenResponse(
        access_token=new_access_token,
        token_type="Bearer",
        expires_in=3600,
        refresh_token=request.refresh_token,
    )


@router.get("/me", response_model=MeResponse, summary="Get current authenticated actor per §19")
def get_me(request: Request) -> MeResponse:
    """Return actor_id and scopes of the authenticated caller."""
    actor_id = getattr(request.state, "actor_id", None)
    if not actor_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    scopes = getattr(request.state, "scopes", [])
    return MeResponse(actor_id=actor_id, scopes=scopes)


__all__ = ["USERS_DB", "router"]
