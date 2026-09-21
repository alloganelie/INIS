"""FastAPI application entrypoint for INIS API."""

from __future__ import annotations

import os
import subprocess

from fastapi import FastAPI

# Individual sub-router imports — mounted directly for FastAPI 0.141+ compatibility.
# app/api/v1/router.py is kept intact but no longer used by main.py.
from app.api.v1.agents.router import router as agents_router
from app.api.v1.auth.router import router as auth_router
from app.api.v1.confidence.router import router as confidence_router
from app.api.v1.conflicts.router import router as conflicts_router
from app.api.v1.evidence.router import router as evidence_router
from app.api.v1.information.router import router as information_router
from app.api.v1.quality.router import router as quality_router
from app.api.v1.requests.progress_handler import router as progress_router
from app.api.v1.requests.router import router as requests_router
from app.api.v1.sources.router import router as sources_router
from app.api.v1.system.changelog_router import router as changelog_router
from app.api.v1.system.health_router import router as health_router
from app.api.v1.system.metrics_router import router as metrics_router

API_VERSION = "0.1.0"


def _resolve_commit_sha() -> str:
    """Resolve current git commit SHA or return 'unknown'."""
    commit = os.getenv("GIT_COMMIT") or os.getenv("COMMIT_SHA")
    if commit:
        return commit
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
            timeout=2,
        )
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip()
    except Exception:
        pass
    return "unknown"


app = FastAPI(
    title="INIS API",
    version=API_VERSION,
    docs_url="/v1/docs",
    openapi_url="/v1/openapi.json",
)

try:
    from app.api.middleware.auth_middleware import AuthMiddleware

    app.add_middleware(AuthMiddleware)
except ImportError:
    pass


@app.get("/health")
def get_health() -> dict[str, str]:
    """Health check endpoint returning status and API version."""
    return {"status": "ok", "version": API_VERSION}


@app.get("/version")
def get_version() -> dict[str, str]:
    """Version metadata endpoint returning API version and git commit."""
    return {"version": API_VERSION, "commit": _resolve_commit_sha()}


@app.get("/v1/status")
def get_v1_status() -> dict[str, str]:
    """Status endpoint returning operational readiness."""
    return {"status": "ready"}


# Mount each sub-router individually with prefix="/v1".
# Each router already carries its own internal prefix (e.g. /auth, /sources),
# so the final paths become /v1/auth/*, /v1/sources/*, etc.
app.include_router(auth_router, prefix="/v1")
app.include_router(requests_router, prefix="/v1")
app.include_router(progress_router, prefix="/v1")
app.include_router(agents_router, prefix="/v1")
app.include_router(sources_router, prefix="/v1")
app.include_router(information_router, prefix="/v1")
app.include_router(evidence_router, prefix="/v1")
app.include_router(conflicts_router, prefix="/v1")
app.include_router(quality_router, prefix="/v1")
app.include_router(confidence_router, prefix="/v1")
app.include_router(changelog_router, prefix="/v1")
app.include_router(metrics_router, prefix="/v1")
app.include_router(health_router, prefix="/v1")

