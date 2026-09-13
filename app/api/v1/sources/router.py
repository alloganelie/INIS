"""Router for Sources."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status

from app.api.v1.sources.schemas import SourceCreate, SourceList, SourceResponse
from app.domain.value_objects.ulid import ULID

router = APIRouter(prefix="/sources", tags=["sources"])

_SOURCES_STORE: dict[str, SourceResponse] = {}


@router.get(
    "",
    response_model=SourceList,
    summary="List registered sources",
)
def list_sources(source_type: str | None = None) -> SourceList:
    """Return all sources, optionally filtered by source_type."""
    sources = list(_SOURCES_STORE.values())
    if source_type:
        sources = [s for s in sources if s.source_type == source_type]
    return SourceList(sources=sources, items=sources, total=len(sources))


@router.post(
    "",
    response_model=SourceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new source",
)
def create_source(payload: SourceCreate) -> SourceResponse:
    """Register a new source and return its generated source_id."""
    src_id = ULID.new("SRC_")
    now = datetime.now(timezone.utc).isoformat()
    item = SourceResponse(
        source_id=src_id,
        name=payload.name,
        source_type=payload.source_type,
        url=payload.url,
        description=payload.description,
        trust_level=payload.trust_level,
        status=payload.status,
        metadata=payload.metadata,
        created_at=now,
        updated_at=now,
    )
    _SOURCES_STORE[src_id] = item
    return item


@router.get(
    "/{id}",
    response_model=SourceResponse,
    summary="Get a source by ID",
)
def get_source(id: str) -> SourceResponse:
    """Retrieve an existing source by its ID or return 404."""
    if id not in _SOURCES_STORE:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source '{id}' not found",
        )
    return _SOURCES_STORE[id]
