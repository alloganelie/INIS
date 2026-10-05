"""Router for Evidence per §14.2 and §32."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.api.v1.evidence.schemas import (
    EvidenceCreate,
    EvidenceList,
    EvidenceResponse,
)
from app.core.time import utc_now
from app.domain.value_objects.ulid import ULID
from app.storage.repositories.evidence_repository import (
    EvidenceRepository,
    get_database_engine,
)

router = APIRouter(prefix="/evidence", tags=["evidence"])

_EVIDENCE_STORE: dict[str, EvidenceResponse] = {}


@router.get(
    "",
    response_model=EvidenceList,
    summary="List evidence items, optionally filtered by claim_id",
)
async def list_evidence(
    claim_id: str | None = None,
    source_id: str | None = None,
    information_id: str | None = None,
) -> EvidenceList:
    """Return stored evidence items, optionally filtered by claim_id, source_id, or information_id."""
    engine = get_database_engine()
    if engine is not None:
        data = await EvidenceRepository.list(
            engine,
            claim_id=claim_id,
            source_id=source_id,
            information_id=information_id,
        )
        items = [EvidenceResponse(**d) for d in data]
        return EvidenceList(items=items, evidence=items, total=len(items))

    items = list(_EVIDENCE_STORE.values())
    if claim_id is not None:
        items = [e for e in items if e.claim_id == claim_id]
    if source_id is not None:
        items = [e for e in items if e.source_id == source_id]
    if information_id is not None:
        items = [e for e in items if e.information_id == information_id]
    return EvidenceList(items=items, evidence=items, total=len(items))


@router.post(
    "",
    response_model=EvidenceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record new evidence",
)
async def create_evidence(payload: EvidenceCreate) -> EvidenceResponse:
    """Record a new evidence entry and return its generated evidence_id."""
    evidence_id = ULID.new("EVID_")
    now = utc_now().isoformat()
    evidence_dict = {
        "evidence_id": evidence_id,
        "claim_id": payload.claim_id,
        "information_id": payload.information_id,
        "source_id": payload.source_id,
        "document_id": payload.document_id,
        "dataset_id": payload.dataset_id,
        "transformation_id": payload.transformation_id,
        "excerpt": payload.excerpt,
        "location": payload.location,
        "strength": payload.strength,
        "confidence": payload.confidence,
        "provenance": payload.provenance,
        "epistemic_status": payload.epistemic_status,
        "created_at": now,
    }

    engine = get_database_engine()
    if engine is not None:
        saved = await EvidenceRepository.create(engine, evidence_dict)
        item = EvidenceResponse(**saved)
        _EVIDENCE_STORE[evidence_id] = item
        return item

    item = EvidenceResponse(**evidence_dict)
    _EVIDENCE_STORE[evidence_id] = item
    return item


@router.get(
    "/{id}",
    response_model=EvidenceResponse,
    summary="Get an evidence item by ID",
)
async def get_evidence(id: str) -> EvidenceResponse:
    """Retrieve an existing evidence item by its ID or return 404."""
    engine = get_database_engine()
    if engine is not None:
        saved = await EvidenceRepository.get(engine, id)
        if saved is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Evidence '{id}' not found",
            )
        return EvidenceResponse(**saved)

    if id not in _EVIDENCE_STORE:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evidence '{id}' not found",
        )
    return _EVIDENCE_STORE[id]

