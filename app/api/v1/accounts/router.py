"""Router for Account management per §19 and §32."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Response, status
from ulid import ULID as PythonUlid

from app.api.v1.accounts.password_hasher import PasswordHasher
from app.api.v1.accounts.schemas import (
    AccountCreateRequest,
    AccountResponse,
    AccountUpdateRequest,
    ChangePasswordRequest,
)

router = APIRouter(prefix="/accounts", tags=["accounts"])

# In-memory store for account entities: id -> account dict
_ACCOUNTS_STORE: dict[str, dict[str, Any]] = {}


def get_account_repository() -> Any | None:
    """Return AccountRepository instance if INIS_DATABASE_URL is set and repository exists."""
    db_url = os.getenv("INIS_DATABASE_URL")
    if not db_url:
        return None
    try:
        from app.storage.repositories.account_repository import AccountRepository

        return AccountRepository
    except ImportError:
        return None


def reset_accounts_store() -> None:
    """Reset in-memory accounts store for testing."""
    _ACCOUNTS_STORE.clear()


def find_account(username_or_email: str) -> dict[str, Any] | None:
    """Find an active or registered account by username or email."""
    target = username_or_email.lower().strip()
    for acc in _ACCOUNTS_STORE.values():
        if acc["username"].lower().strip() == target or acc["email"].lower().strip() == target:
            return acc
    return None


def get_account_by_id(account_id: str) -> dict[str, Any] | None:
    """Find account by unique ID."""
    return _ACCOUNTS_STORE.get(account_id)


@router.post(
    "",
    response_model=AccountResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account per §19.2",
)
def create_account(payload: AccountCreateRequest) -> AccountResponse:
    """Create a new account with hashed password and unique identifier."""
    # Check for duplicates
    for acc in _ACCOUNTS_STORE.values():
        if acc["username"].lower() == payload.username.lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Account with username '{payload.username}' already exists",
            )
        if acc["email"].lower() == payload.email.lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Account with email '{payload.email}' already exists",
            )

    repo = get_account_repository()
    if repo is not None and hasattr(repo, "create"):
        try:
            created = repo.create(payload)
            return AccountResponse(**created)
        except Exception:
            pass  # Fall back to in-memory store

    account_id = f"ACC_{PythonUlid()}"
    now = datetime.now(timezone.utc).isoformat()
    account_data = {
        "id": account_id,
        "username": payload.username,
        "email": payload.email,
        "hashed_password": PasswordHasher.hash(payload.password),
        "role": payload.role,
        "scopes": payload.scopes,
        "is_active": True,
        "status": "active",
        "created_at": now,
        "updated_at": now,
    }
    _ACCOUNTS_STORE[account_id] = account_data
    return AccountResponse(**account_data)


@router.get(
    "/{account_id}",
    response_model=AccountResponse,
    summary="Get account details by ID per §19.2",
)
def get_account(account_id: str) -> AccountResponse:
    """Retrieve account details by ID."""
    repo = get_account_repository()
    if repo is not None and hasattr(repo, "get"):
        try:
            account = repo.get(account_id)
            if account:
                return AccountResponse(**account)
        except Exception:
            pass

    account = _ACCOUNTS_STORE.get(account_id)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account '{account_id}' not found",
        )
    return AccountResponse(**account)


@router.patch(
    "/{account_id}",
    response_model=AccountResponse,
    summary="Update account properties per §19.2",
)
def update_account(account_id: str, payload: AccountUpdateRequest) -> AccountResponse:
    """Update email, password, role, scopes or active status."""
    repo = get_account_repository()
    if repo is not None and hasattr(repo, "update"):
        try:
            updated = repo.update(account_id, payload)
            if updated:
                return AccountResponse(**updated)
        except Exception:
            pass

    account = _ACCOUNTS_STORE.get(account_id)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account '{account_id}' not found",
        )

    if payload.email is not None and payload.email.lower() != account["email"].lower():
        for other_id, other_acc in _ACCOUNTS_STORE.items():
            if other_id != account_id and other_acc["email"].lower() == payload.email.lower():
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Account with email '{payload.email}' already exists",
                )
        account["email"] = payload.email

    if payload.password is not None:
        account["hashed_password"] = PasswordHasher.hash(payload.password)

    if payload.role is not None:
        account["role"] = payload.role

    if payload.scopes is not None:
        account["scopes"] = payload.scopes

    if payload.is_active is not None:
        account["is_active"] = payload.is_active
        account["status"] = "active" if payload.is_active else "deleted"

    account["updated_at"] = datetime.now(timezone.utc).isoformat()
    return AccountResponse(**account)


@router.delete(
    "/{account_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft delete an account per §0.2 and §19.2",
)
def delete_account(account_id: str) -> Response:
    """Soft delete account by marking status as deleted and is_active as False."""
    repo = get_account_repository()
    if repo is not None and hasattr(repo, "delete"):
        try:
            repo.delete(account_id)
            return Response(status_code=status.HTTP_204_NO_CONTENT)
        except Exception:
            pass

    account = _ACCOUNTS_STORE.get(account_id)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account '{account_id}' not found",
        )

    account["is_active"] = False
    account["status"] = "deleted"
    account["updated_at"] = datetime.now(timezone.utc).isoformat()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{account_id}/change-password",
    summary="Change account password per §19.2",
)
def change_password(account_id: str, payload: ChangePasswordRequest) -> dict[str, str]:
    """Verify old password and update to new password."""
    account = _ACCOUNTS_STORE.get(account_id)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account '{account_id}' not found",
        )

    if not PasswordHasher.verify(payload.old_password, account["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect current password",
        )

    account["hashed_password"] = PasswordHasher.hash(payload.new_password)
    account["updated_at"] = datetime.now(timezone.utc).isoformat()
    return {"status": "success", "message": "Password changed successfully"}


__all__ = [
    "create_account",
    "delete_account",
    "find_account",
    "get_account",
    "get_account_by_id",
    "reset_accounts_store",
    "router",
    "update_account",
]
