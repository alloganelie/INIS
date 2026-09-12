"""FastAPI application entrypoint for INIS API."""

from __future__ import annotations

import os
import subprocess

from fastapi import FastAPI

from app.api.v1.router import router as v1_router

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


@app.get("/health")
def get_health() -> dict[str, str]:
    """Health check endpoint returning status and API version."""
    return {"status": "ok", "version": API_VERSION}


@app.get("/version")
def get_version() -> dict[str, str]:
    """Version metadata endpoint returning API version and git commit."""
    return {"version": API_VERSION, "commit": _resolve_commit_sha()}


app.include_router(v1_router)
