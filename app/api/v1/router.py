"""INIS API v1 router."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/v1", tags=["v1"])


@router.get("/status")
def get_status() -> dict[str, str]:
    """Status endpoint returning operational readiness."""
    return {"status": "ready"}
