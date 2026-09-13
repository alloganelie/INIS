"""INIS API v1 router."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.agents.router import router as agents_router
from app.api.v1.information.router import router as information_router
from app.api.v1.requests.router import router as requests_router
from app.api.v1.sources.router import router as sources_router

router = APIRouter(prefix="/v1", tags=["v1"])


@router.get("/status")
def get_status() -> dict[str, str]:
    """Status endpoint returning operational readiness."""
    return {"status": "ready"}


router.include_router(requests_router)
router.include_router(agents_router)
router.include_router(sources_router)
router.include_router(information_router)

