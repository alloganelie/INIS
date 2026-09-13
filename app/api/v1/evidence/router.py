"""Router for Evidence per §14.2 and §32."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status

from app.api.v1.evidence.schemas import (
    EvidenceCreate,
    EvidenceList,
    EvidenceResponse,
)
from app.domain.value_objects.ulid import ULID

router = APIRouter(prefix="/evidence", tags=["evidence"])

_EVIDENCE_STORE: dict[str, EvidenceResponse] = {}


@router.get(
    "",
    response_model=EvidenceList,
    summary="List evidence items, optionally filtered by claim_id",
)
def list_evidence(claim_id: str | None = None) -> EvidenceList:
    """Return stored evidence items, optionally filtered by claim_id."""
    items = list(_EVIDENCE_STORE.values())
    if claim_id is not None:
        items = [e for e in items if e.claim_id == claim_id]
    return EvidenceList(items=items, evidence=items, total=len(items))


@router.post(
    "",
    response_model=EvidenceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record new evidence",
)
def create_evidence(payload: EvidenceCreate) -> EvidenceResponse:
    """Record a new evidence entry and return its generated evidence_id."""
    evidence_id = ULID.new("EVID_")
    now = datetime.now(timezone.utc).isoformat()
    item = EvidenceResponse(
        evidence_id=evidence_id,
        claim_id=payload.claim_id,
        information_id=payload.information_id,
        source_id=payload.source_id,
        document_id=payload.document_id,
        dataset_id=payload.dataset_id,
        transformation_id=payload.transformation_id,
        excerpt=payload.excerpt,
        location=payload.location,
        strength=payload.strength,
        confidence=payload.confidence,
        provenance=payload.provenance,
        epistemic_status=payload.epistemic_status,
        created_at=now,
    )
    _EVIDENCE_STORE[evidence_id] = item
    return item


@router.get(
    "/{id}",
    response_model=EvidenceResponse,
    summary="Get an evidence item by ID",
)
def get_evidence(id: str) -> EvidenceResponse:
    """Retrieve an existing evidence item by its ID or return 404."""
    if id not in _EVIDENCE_STORE:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evidence '{id}' not found",
        )
    return _EVIDENCE_STORE[id]
