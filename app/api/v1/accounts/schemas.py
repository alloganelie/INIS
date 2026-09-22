"""Pydantic schemas for account management per §19 and §32."""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class AccountCreateRequest(BaseModel):
    """Payload to register a new account."""

    username: str = Field(..., min_length=3, max_length=64, description="Unique username")
    email: str = Field(..., min_length=5, max_length=255, description="Unique email address")
    password: str = Field(..., min_length=6, description="Plain text password")
    role: str = Field(default="operator", description="Account role (admin, operator, reader)")
    scopes: list[str] = Field(
        default_factory=lambda: ["read", "write"],
        description="Assigned permissions and scopes",
    )


class AccountResponse(BaseModel):
    """Account representation returned by the API."""

    id: str = Field(..., description="Unique account identifier (ULID prefixed ACC_)")
    username: str = Field(..., description="Account username")
    email: str = Field(..., description="Account email address")
    role: str = Field(..., description="Assigned role")
    scopes: list[str] = Field(default_factory=list, description="Assigned authorization scopes")
    is_active: bool = Field(default=True, description="Whether the account is active")
    status: str = Field(default="active", description="Account lifecycle status (active, deleted)")
    created_at: str = Field(..., description="ISO 8601 UTC creation timestamp")
    updated_at: str = Field(..., description="ISO 8601 UTC last update timestamp")


class AccountUpdateRequest(BaseModel):
    """Payload to update an existing account."""

    email: str | None = Field(default=None, min_length=5, max_length=255, description="New email address")
    password: str | None = Field(default=None, min_length=6, description="New plain text password")
    role: str | None = Field(default=None, description="New role")
    scopes: list[str] | None = Field(default=None, description="New list of scopes")
    is_active: bool | None = Field(default=None, description="Active status")


class LoginRequest(BaseModel):
    """Credentials required to authenticate."""

    username: str = Field(..., description="Username or email address")
    password: str = Field(..., description="Plain text password")


class LoginResponse(BaseModel):
    """JWT response after successful authentication."""

    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field(default="Bearer", description="Token type")
    expires_in: int = Field(default=3600, description="Access token expiration in seconds")
    refresh_token: str | None = Field(default=None, description="Refresh token")


class ChangePasswordRequest(BaseModel):
    """Payload to update an account's password."""

    old_password: str = Field(..., description="Current password")
    new_password: str = Field(..., min_length=6, description="New password")


__all__ = [
    "AccountCreateRequest",
    "AccountResponse",
    "AccountUpdateRequest",
    "ChangePasswordRequest",
    "LoginRequest",
    "LoginResponse",
]
