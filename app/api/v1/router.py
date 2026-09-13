"""INIS API v1 router."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.agents.router import router as agents_router
from app.api.v1.conflicts.router import router as conflicts_router
from app.api.v1.evidence.router import router as evidence_router
from app.api.v1.information.router import router as information_router
from app.api.v1.requests.progress_handler import router as progress_router
from app.api.v1.requests.router import router as requests_router
from app.api.v1.sources.router import router as sources_router
from app.api.v1.system.changelog_router import router as changelog_router
from app.api.v1.system.health_router import router as health_router
from app.api.v1.system.metrics_router import router as metrics_router

router = APIRouter(prefix="/v1", tags=["v1"])


@router.get("/status")
def get_status() -> dict[str, str]:
    """Status endpoint returning operational readiness."""
    return {"status": "ready"}


router.include_router(requests_router)
router.include_router(progress_router)
router.include_router(agents_router)
router.include_router(sources_router)
router.include_router(information_router)
router.include_router(evidence_router)
router.include_router(conflicts_router)
router.include_router(changelog_router)
router.include_router(metrics_router)
router.include_router(health_router)


