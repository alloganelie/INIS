"""Pydantic schemas for authentication endpoints per §19 and §32."""

from __future__ import annotations

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """User credentials for authentication."""

    username: str = Field(..., description="Username or actor identifier")
    password: str = Field(..., description="Password or secret")


class TokenResponse(BaseModel):
    """Authentication token response per §19.2."""

    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field(default="Bearer", description="Token type")
    expires_in: int = Field(default=3600, description="Expiration time in seconds")
    refresh_token: str | None = Field(default=None, description="Optional refresh token")


class RefreshRequest(BaseModel):
    """Token refresh request."""

    refresh_token: str = Field(..., description="JWT refresh token")


class MeResponse(BaseModel):
    """Current authenticated actor information."""

    actor_id: str = Field(..., description="Authenticated actor identifier")
    scopes: list[str] = Field(default_factory=list, description="Granted authorization scopes")


__all__ = [
    "LoginRequest",
    "MeResponse",
    "RefreshRequest",
    "TokenResponse",
]
