"""Router for Sources."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status

from app.api.v1.sources.repository import SourceRepository, get_database_engine
from app.api.v1.sources.schemas import SourceCreate, SourceList, SourceResponse
from app.domain.value_objects.ulid import ULID

router = APIRouter(prefix="/sources", tags=["sources"])

_SOURCES_STORE: dict[str, SourceResponse] = {}


@router.get(
    "",
    response_model=SourceList,
    summary="List registered sources",
)
async def list_sources(source_type: str | None = None) -> SourceList:
    """Return all sources, optionally filtered by source_type."""
    engine = get_database_engine()
    if engine is not None:
        data = await SourceRepository.list(engine, source_type=source_type)
        sources = [SourceResponse(**d) for d in data]
        return SourceList(sources=sources, items=sources, total=len(sources))

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
async def create_source(payload: SourceCreate) -> SourceResponse:
    """Register a new source and return its generated source_id."""
    src_id = ULID.new("SRC_")
    now = datetime.now(timezone.utc).isoformat()
    source_dict = {
        "source_id": src_id,
        "name": payload.name,
        "source_type": payload.source_type,
        "url": payload.url,
        "description": payload.description,
        "trust_level": payload.trust_level,
        "status": payload.status,
        "metadata": payload.metadata,
        "created_at": now,
        "updated_at": now,
    }

    engine = get_database_engine()
    if engine is not None:
        saved = await SourceRepository.create(engine, source_dict)
        item = SourceResponse(**saved)
        _SOURCES_STORE[src_id] = item
        return item

    item = SourceResponse(**source_dict)
    _SOURCES_STORE[src_id] = item
    return item


@router.get(
    "/{id}",
    response_model=SourceResponse,
    summary="Get a source by ID",
)
async def get_source(id: str) -> SourceResponse:
    """Retrieve an existing source by its ID or return 404."""
    engine = get_database_engine()
    if engine is not None:
        saved = await SourceRepository.get(engine, id)
        if saved is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Source '{id}' not found",
            )
        return SourceResponse(**saved)

    if id not in _SOURCES_STORE:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source '{id}' not found",
        )
    return _SOURCES_STORE[id]
