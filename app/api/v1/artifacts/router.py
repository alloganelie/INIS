"""Router for the delivered artifacts (§24.2, §32).

Before this router existed, a delivery announced ``artifacts`` and no endpoint
could list or fetch them: the §24.2 record was built in memory and thrown away,
and the frontend hid the hole behind ``catch { return [] }``. The three routes
below close that loop:

* ``GET /v1/artifacts?request_id=…`` — the artifacts delivered for a request;
* ``GET /v1/artifacts/{artifact_id}`` — one §24.2 record;
* ``GET /v1/artifacts/{artifact_id}/download`` — the bytes themselves.

Honesty rules of this router (they are what the tests assert):

* an unknown identifier is a **404**, never an empty 200;
* an artifact whose bytes were never stored (``unavailable://``: no object
  storage configured at delivery time) is a **503** naming the reason, never a
  404 claiming it never existed;
* with no database configured, listing is only possible for a request the
  runner still holds in memory — anything else is a **503** instead of a silent
  empty list (§25.2).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import Response

from app.api.v1.artifacts.schemas import ArtifactList, ArtifactResponse
from app.api.v1.requests.pipeline_runner import pipeline_runner
from app.artifacts.packager.artifact_packager import UNSTORED_REF_SCHEME
from app.storage.object_storage.object_storage_factory import (
    build_object_storage,
    split_storage_ref,
)
from app.storage.repositories.artifact_repository import ArtifactRepository
from app.storage.repositories.information_unit_repository import get_database_engine

router = APIRouter(prefix="/artifacts", tags=["artifacts"])

#: Explains the missing-database degradation of every route below.
_NO_PERSISTENCE = (
    "Artifacts are not persisted (INIS_DATABASE_URL not configured): only a request "
    "still held in memory by the running pipeline can be inspected."
)


def _records_from_pipeline_state(request_id: str) -> list[dict] | None:
    """Return the artifacts a live run holds, or ``None`` for an unknown request."""
    state = pipeline_runner.get_state(request_id)
    if state is None:
        return None
    return [dict(record) for record in state.get("artifacts") or []]


@router.get(
    "",
    response_model=ArtifactList,
    summary="List delivered artifacts, optionally filtered by request_id (§24.2)",
)
async def list_artifacts(
    request_id: str | None = Query(default=None, description="Filter by request_id"),
    limit: int = Query(default=100, ge=1, le=500),
) -> ArtifactList:
    """Return the §24.2 artifacts delivered for a request (or all of them)."""
    engine = get_database_engine()
    if engine is not None:
        if request_id:
            rows = await ArtifactRepository.list_for_request(engine, request_id, limit)
        else:
            rows = await ArtifactRepository.list_all(engine, limit)
        items = [ArtifactResponse(**row) for row in rows]
        return ArtifactList(artifacts=items, total=len(items))

    if not request_id:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=_NO_PERSISTENCE)

    records = _records_from_pipeline_state(request_id)
    if records is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Information request '{request_id}' not found",
        )
    items = [ArtifactResponse(**record) for record in records[:limit]]
    return ArtifactList(artifacts=items, total=len(items))


@router.get(
    "/{artifact_id}",
    response_model=ArtifactResponse,
    summary="Get one artifact by ID (§24.2)",
)
async def get_artifact(artifact_id: str) -> ArtifactResponse:
    """Return one §24.2 artifact, or 404 when it was never delivered."""
    engine = get_database_engine()
    if engine is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=_NO_PERSISTENCE)

    record = await ArtifactRepository.get(engine, artifact_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artifact '{artifact_id}' not found",
        )
    return ArtifactResponse(**record)


@router.get(
    "/{artifact_id}/download",
    summary="Download the bytes of an artifact (§24.2)",
)
async def download_artifact(artifact_id: str) -> Response:
    """Return the delivered file with its §24.2 ``mime_type`` and name."""
    engine = get_database_engine()
    if engine is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=_NO_PERSISTENCE)

    record = await ArtifactRepository.get(engine, artifact_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artifact '{artifact_id}' not found",
        )

    storage_ref = str(record.get("storage_ref") or "")
    if storage_ref.startswith(UNSTORED_REF_SCHEME):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                f"Artifact '{artifact_id}' exists but its bytes were never stored "
                f"(storage_ref={storage_ref}): object storage was not available when it "
                "was delivered."
            ),
        )

    storage = build_object_storage()
    if storage is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Object storage is not configured (S3_ENDPOINT, S3_ACCESS_KEY, "
                "S3_SECRET_KEY, S3_BUCKET): the artifact cannot be retrieved."
            ),
        )

    location = split_storage_ref(storage_ref)
    if location is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Artifact '{artifact_id}' has an unsupported storage_ref '{storage_ref}'.",
        )
    _, key = location
    try:
        content = storage.download(key)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                f"Object storage refused to return '{storage_ref}' "
                f"({type(exc).__name__}: {exc})."
            ),
        ) from exc

    file_name = str(record.get("file_name") or f"{artifact_id}.bin")
    return Response(
        content=content,
        media_type=str(record.get("mime_type") or "application/octet-stream"),
        headers={"Content-Disposition": f'attachment; filename="{file_name}"'},
    )
