"""Health router providing health and readiness endpoints per §32, §34."""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.v1.sources.repository import get_database_engine

router = APIRouter(prefix="/health", tags=["system"])

_BROKER_CHECK: Any | None = None


def set_broker_check(broker: Any | None) -> None:
    """Register an active broker or callable for readiness probe testing."""
    global _BROKER_CHECK
    _BROKER_CHECK = broker


@router.get(
    "",
    summary="Basic liveness check per §32",
)
def get_health() -> dict[str, str]:
    """Basic health check returning operational status."""
    return {"status": "ok", "version": "0.1.0"}


@router.get(
    "/ready",
    summary="Subsystem readiness check per §32, §34",
)
async def get_health_ready() -> JSONResponse:
    """Check database and broker readiness.

    Returns HTTP 200 if all checks are ready, HTTP 503 otherwise.
    Format: {"status": "ready" | "not_ready", "checks": {...}}
    """
    checks: dict[str, Any] = {}
    is_ready = True

    # 1. Database check (SELECT 1)
    db_url = os.getenv("INIS_DATABASE_URL")
    if db_url:
        try:
            engine = get_database_engine()
            if engine is not None:
                async with engine.connect() as conn:
                    await conn.execute(text("SELECT 1"))
                checks["database"] = {"status": "ready"}
            else:
                checks["database"] = {
                    "status": "not_ready",
                    "error": "database engine unavailable",
                }
                is_ready = False
        except Exception as exc:
            checks["database"] = {"status": "not_ready", "error": str(exc)}
            is_ready = False
    else:
        # In-memory mode is default and operational
        checks["database"] = {"status": "ready", "detail": "in_memory"}

    # 2. Broker check (if applicable)
    broker_obj = _BROKER_CHECK
    broker_configured = broker_obj is not None or bool(
        os.getenv("AMQP_URL") or os.getenv("INIS_BROKER_URL")
    )

    if broker_configured:
        if broker_obj is not None:
            try:
                if callable(broker_obj):
                    res = broker_obj()
                    if hasattr(res, "__await__"):
                        res = await res
                    if isinstance(res, dict) and res.get("status") in ("up", "ready"):
                        checks["broker"] = {"status": "ready"}
                    elif res is True:
                        checks["broker"] = {"status": "ready"}
                    else:
                        checks["broker"] = {"status": "not_ready", "detail": res}
                        is_ready = False
                elif hasattr(broker_obj, "is_connected"):
                    if broker_obj.is_connected:
                        checks["broker"] = {"status": "ready"}
                    else:
                        checks["broker"] = {
                            "status": "not_ready",
                            "error": "broker is not connected",
                        }
                        is_ready = False
                else:
                    checks["broker"] = {"status": "ready"}
            except Exception as exc:
                checks["broker"] = {"status": "not_ready", "error": str(exc)}
                is_ready = False
        else:
            checks["broker"] = {
                "status": "not_ready",
                "error": "broker configured but no connected instance found",
            }
            is_ready = False
    else:
        checks["broker"] = {"status": "ready", "detail": "not_applicable"}

    overall_status = "ready" if is_ready else "not_ready"
    http_status = (
        status.HTTP_200_OK if is_ready else status.HTTP_503_SERVICE_UNAVAILABLE
    )

    return JSONResponse(
        status_code=http_status,
        content={
            "status": overall_status,
            "checks": checks,
        },
    )
