"""API middleware package."""

from app.api.middleware.auth_middleware import AuthMiddleware

__all__ = ["AuthMiddleware"]
