"""Router for Account management per §19 and §32.

Persistence rule (B4-bis constat 2): when ``INIS_DATABASE_URL`` is set the
``accounts`` table is the single source of truth and a database failure is a
real error (HTTP 503), never a silent in-memory fallback. The in-memory store
is used **only** when no database is configured at all.
"""

from __future__ import annotations

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
from app.storage.database.session import account_repository, database_configured

router = APIRouter(prefix="/accounts", tags=["accounts"])

# In-memory store used ONLY when INIS_DATABASE_URL is absent.
_ACCOUNTS_STORE: dict[str, dict[str, Any]] = {}


def reset_accounts_store() -> None:
    """Reset in-memory accounts store for testing."""
    _ACCOUNTS_STORE.clear()


def get_account_repository() -> Any | None:
    """Return the ``AccountRepository`` class when a database is configured.

    Kept for backward compatibility. Prefer the ``account_repository()``
    context manager, which binds a real :class:`AsyncSession` — returning the
    class here is exactly the B4-bis defect (it used to be called as if it were
    an instance, so every call raised and silently fell back to memory).
    """
    if not database_configured():
        return None
    from app.storage.repositories.account_repository import AccountRepository

    return AccountRepository


#: Fallbacks for a row written before migration 0009, and for a JSONB column
#: read back as a string. Never used to invent a value the DB does not hold.
LEGACY_ROLE = "operator"
LEGACY_SCOPES = ["read", "write"]


def _as_scopes(raw: Any) -> list[str]:
    """Return ``accounts.scopes`` as a list, whatever the driver returned."""
    if raw is None:
        return list(LEGACY_SCOPES)
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return list(LEGACY_SCOPES)
    if isinstance(raw, (list, tuple)):
        return [str(item) for item in raw]
    return list(LEGACY_SCOPES)


def _db_account_to_dict(account: Any) -> dict[str, Any]:
    """Project an ``Account`` ORM row onto the API response shape.

    ``role`` and ``scopes`` are read from the row (B4-ter-2): they are no longer
    hardcoded, so a ``role=reader`` account survives an API restart.
    """
    return {
        "id": account.account_id,
        "username": account.username,
        "email": account.email,
        "hashed_password": account.password_hash,
        "role": account.role or LEGACY_ROLE,
        "scopes": _as_scopes(account.scopes),
        "is_active": account.status != "deleted",
        "status": account.status,
        "created_at": account.created_at.isoformat() if account.created_at else None,
        "updated_at": account.updated_at.isoformat() if account.updated_at else None,
    }


async def find_account(username_or_email: str) -> dict[str, Any] | None:
    """Find an active or registered account by username or email."""
    target = username_or_email.lower().strip()
    if database_configured():
        async with account_repository() as repo:
            found = await repo.get_by_username(target)
            if found is None:
                found = await repo.get_by_email(target)
            return _db_account_to_dict(found) if found else None

    for account in _ACCOUNTS_STORE.values():
        if (
            account["username"].lower().strip() == target
            or account["email"].lower().strip() == target
        ):
            return account
    return None


async def get_account_by_id(account_id: str) -> dict[str, Any] | None:
    """Find account by unique ID."""
    if database_configured():
        async with account_repository() as repo:
            found = await repo.get_by_id(account_id)
            return _db_account_to_dict(found) if found else None
    return _ACCOUNTS_STORE.get(account_id)


@router.post(
    "",
    response_model=AccountResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account per §19.2",
)
async def create_account(payload: AccountCreateRequest) -> AccountResponse:
    """Create a new account with hashed password and unique identifier."""
    if database_configured():
        async with account_repository() as repo:
            if await repo.get_by_username(payload.username):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Account with username '{payload.username}' already exists",
                )
            if await repo.get_by_email(payload.email):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Account with email '{payload.email}' already exists",
                )
            account_id = f"ACC_{PythonUlid()}"
            created = await repo.create(
                account_id=account_id,
                username=payload.username,
                email=payload.email,
                password_hash=PasswordHasher.hash(payload.password),
                status="active",
                role=payload.role,
                scopes=payload.scopes,
            )
            await repo.session.commit()
            return AccountResponse(**_db_account_to_dict(created))

    for account in _ACCOUNTS_STORE.values():
        if account["username"].lower() == payload.username.lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Account with username '{payload.username}' already exists",
            )
        if account["email"].lower() == payload.email.lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Account with email '{payload.email}' already exists",
            )

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
async def get_account(account_id: str) -> AccountResponse:
    """Retrieve account details by ID."""
    if database_configured():
        async with account_repository() as repo:
            found = await repo.get_by_id(account_id)
            if found is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Account '{account_id}' not found",
                )
            return AccountResponse(**_db_account_to_dict(found))

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
async def update_account(account_id: str, payload: AccountUpdateRequest) -> AccountResponse:
    """Update email, password, role, scopes or active status."""
    if database_configured():
        async with account_repository() as repo:
            found = await repo.get_by_id(account_id)
            if found is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Account '{account_id}' not found",
                )
            if payload.email is not None and payload.email.lower() != found.email.lower():
                clash = await repo.get_by_email(payload.email)
                if clash is not None:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=f"Account with email '{payload.email}' already exists",
                    )
                found.email = payload.email
            if payload.password is not None:
                await repo.update_password_hash(
                    account_id, PasswordHasher.hash(payload.password)
                )
            if payload.is_active is not None:
                await repo.update_status(
                    account_id, "active" if payload.is_active else "deleted"
                )
            if payload.role is not None or payload.scopes is not None:
                await repo.update_authorization(
                    account_id, role=payload.role, scopes=payload.scopes
                )
            await repo.session.commit()
            return AccountResponse(**_db_account_to_dict(await repo.get_by_id(account_id)))

    account = _ACCOUNTS_STORE.get(account_id)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account '{account_id}' not found",
        )

    if payload.email is not None and payload.email.lower() != account["email"].lower():
        for other_id, other in _ACCOUNTS_STORE.items():
            if other_id != account_id and other["email"].lower() == payload.email.lower():
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
async def delete_account(account_id: str) -> Response:
    """Soft delete account by marking status as deleted and is_active as False."""
    if database_configured():
        async with account_repository() as repo:
            found = await repo.get_by_id(account_id)
            if found is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Account '{account_id}' not found",
                )
            await repo.delete(account_id)
            await repo.session.commit()
            return Response(status_code=status.HTTP_204_NO_CONTENT)

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
async def change_password(account_id: str, payload: ChangePasswordRequest) -> dict[str, str]:
    """Verify old password and update to new password."""
    if database_configured():
        async with account_repository() as repo:
            found = await repo.get_by_id(account_id)
            if found is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Account '{account_id}' not found",
                )
            if not PasswordHasher.verify(payload.old_password, found.password_hash):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Incorrect current password",
                )
            await repo.update_password_hash(
                account_id, PasswordHasher.hash(payload.new_password)
            )
            await repo.session.commit()
            return {"status": "success", "message": "Password changed successfully"}

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
