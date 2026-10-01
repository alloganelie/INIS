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

import hashlib
from collections.abc import Mapping
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import Response

from app.api.middleware.auth_middleware import is_auth_enabled
from app.api.v1.artifacts.schemas import (
    ArtifactDeliveryEventResponse,
    ArtifactLineageResponse,
    ArtifactLineageView,
    ArtifactList,
    ArtifactResponse,
    ArtifactVersionList,
    ArtifactVersionResponse,
)
from app.api.v1.requests.pipeline_runner import pipeline_runner
from app.artifacts.packager.artifact_packager import UNSTORED_REF_SCHEME
from app.core.logging import get_logger
from app.governance.audit.audit_writer import AuditWriter
from app.security.authz.artifact_access import (
    ARTIFACT_READ_ACTION,
    authorize_artifact,
    subject_from_identity,
)
from app.storage.object_storage.object_storage_factory import (
    build_object_storage,
    split_storage_ref,
)
from app.storage.repositories.artifact_repository import ArtifactRepository
from app.storage.repositories.artifact_version_repository import (
    ArtifactDeliveryEventRepository,
    ArtifactLineageRepository,
    ArtifactVersionRepository,
)
from app.storage.repositories.information_unit_repository import get_database_engine

router = APIRouter(prefix="/artifacts", tags=["artifacts"])

logger = get_logger(__name__)


#: Explains the missing-database degradation of every route below.
_NO_PERSISTENCE = (
    "Artifacts are not persisted (INIS_DATABASE_URL not configured): only a request "
    "still held in memory by the running pipeline can be inspected."
)

#: §19.3 — the body of a refusal. It is a **constant**: the caller learns that
#: access was denied, and nothing else. The identifier it probed, the file name,
#: the size, the storage reference and the policy reason all stay out of the
#: response — the reason goes to the audit trail, where it is readable by those
#: allowed to read it.
_ACCESS_DENIED = "Access denied: the caller is not allowed to read this artifact."

#: §18.2 — le corps d'un refus pour artefact supprimé. Comme pour le refus
#: d'autorisation, il ne dit rien de l'artefact lui-même : ni nom, ni empreinte,
#: ni `storage_ref`. La raison précise (statut ou suppression logique) reste dans
#: l'audit.
_ARTIFACT_DELETED = (
    "Artifact is gone: it was deleted and is no longer downloadable (§18.2)."
)


def _subject(request: Request) -> dict[str, Any]:
    """Return the §19.3 subject of the caller, as the middleware identified it."""
    return subject_from_identity(
        getattr(request.state, "actor_id", None),
        getattr(request.state, "scopes", None),
    )


async def _audit_access(
    subject: dict[str, Any],
    *,
    action: str,
    resource_id: str | None,
    outcome: str,
    reason: str,
) -> dict[str, Any]:
    """Write the §20 authorization event; never turn a delivery into a crash.

    An audit that cannot be persisted (no database configured) still reaches the
    structured log — the decision is never silently dropped, it is merely not
    queryable in the database.
    """
    event = {
        "actor_type": "user" if subject.get("actor_id") not in (None, "anonymous") else "anonymous",
        "actor_id": str(subject.get("agent_id") or "anonymous"),
        "action": f"artifact.{action}",
        "resource_type": "artifact",
        "resource_id": resource_id or "",
        "request_id": "",
        "result": outcome,
        "reason": reason,
    }
    engine = get_database_engine()
    try:
        if engine is None:
            # No database: the decision is still recorded — in the structured
            # log — but the event is not claimable as persisted.
            logger.info("artifact_access", **event)
            return {**event, "persisted": False}
        return await AuditWriter(engine).write(event)
    except Exception as exc:  # noqa: BLE001 - §25.2: an audit failure is reported
        logger.warning(
            "artifact access event not persisted", outcome=outcome, error=str(exc)
        )
        return {**event, "persisted": False, "error": f"{type(exc).__name__}: {exc}"}


async def _require_read_access(
    request: Request, record: dict[str, Any] | None = None, *, resource_id: str | None = None
) -> dict[str, Any]:
    """Refuse a caller that may not read the artifact (§19.3), and audit it.

    Two calls, two purposes: ``record=None`` is the check made **before** any
    lookup — it needs no attribute and therefore reveals nothing; the call with a
    ``record`` applies the rules carried by the resource (classification,
    conditions). Both go through :func:`authorize_artifact`, so the decision is
    pronounced by the same §19.3 code in both cases.
    """
    subject = _subject(request)
    decision = authorize_artifact(
        subject, record, action=ARTIFACT_READ_ACTION, require_role=is_auth_enabled()
    )
    await _audit_access(
        subject,
        action=ARTIFACT_READ_ACTION,
        resource_id=resource_id or (record or {}).get("artifact_id"),
        outcome="success" if decision.allowed else "denied",
        reason=decision.reason,
    )
    if not decision.allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_ACCESS_DENIED)
    return subject


def _deletion_of(record: Mapping[str, Any]) -> str | None:
    """Return how *record* is deleted, or ``None`` when it is still served.

    Two marks mean "gone" and both are checked here, because both are real in
    this codebase:

    * ``status == "deleted"`` — the §18.2 status, which the plan's L1 asks to
      refuse;
    * ``deleted_at`` set — the soft delete of decision ``0016``, which hides the
      row from nothing on its own (the repositories keep it readable).
    """
    if str(record.get("status") or "").strip().lower() == "deleted":
        return "status=deleted (§18.2)"
    if record.get("deleted_at"):
        return "deleted_at renseigné (décision 0016)"
    return None


async def _require_not_deleted(request: Request, record: Mapping[str, Any]) -> None:
    """Refuse a deleted artifact **before** anything is read from storage.

    The refusal is a ``410 Gone``: the artifact existed, it is not available any
    more — a ``404`` would claim it was never delivered, which is a different
    (and false) statement. It is audited like every other refusal, so the reason
    lives in the trail and not in the response body.
    """
    marker = _deletion_of(record)
    if marker is None:
        return
    subject = _subject(request)
    await _audit_access(
        subject,
        action=ARTIFACT_READ_ACTION,
        resource_id=str(record.get("artifact_id") or ""),
        outcome="denied",
        reason=f"artifact is deleted ({marker}) — §18.2",
    )
    raise HTTPException(status_code=status.HTTP_410_GONE, detail=_ARTIFACT_DELETED)


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
    request: Request,
    request_id: str | None = Query(default=None, description="Filter by request_id"),
    limit: int = Query(default=100, ge=1, le=500),
) -> ArtifactList:
    """Return the §24.2 artifacts delivered for a request (or all of them).

    §19.3 — what a caller cannot read is not listed. The refusal is pronounced
    **before** the lookup when authentication is configured, and every artifact
    that survives the lookup is still checked individually: a list is not a
    permission to read what it contains.
    """
    await _require_read_access(request)
    engine = get_database_engine()
    if engine is not None:
        if request_id:
            rows = await ArtifactRepository.list_for_request(engine, request_id, limit)
        else:
            rows = await ArtifactRepository.list_all(engine, limit)
        readable: list[ArtifactResponse] = []
        for row in rows:
            subject = _subject(request)
            decision = authorize_artifact(subject, row, require_role=is_auth_enabled())
            if not decision.allowed:
                await _audit_access(
                    subject,
                    action=ARTIFACT_READ_ACTION,
                    resource_id=row.get("artifact_id"),
                    outcome="denied",
                    reason=f"filtered out of the list: {decision.reason}",
                )
                continue
            if _deletion_of(row) is not None:
                # §18.2 — un artefact supprimé ne s'expose pas dans une liste : il
                # ne doit être lisible ni par le détail, ni par le téléchargement,
                # ni ici. Rien n'est dit dans le corps, la trace est dans l'audit.
                await _audit_access(
                    subject,
                    action=ARTIFACT_READ_ACTION,
                    resource_id=row.get("artifact_id"),
                    outcome="denied",
                    reason=f"filtered out of the list: deleted ({_deletion_of(row)}) — §18.2",
                )
                continue
            readable.append(ArtifactResponse(**row))
        return ArtifactList(artifacts=readable, total=len(readable))

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
async def get_artifact(artifact_id: str, request: Request) -> ArtifactResponse:
    """Return one §24.2 artifact, or 404 when it was never delivered.

    §19.3 — the same check as the download: reading the *metadata* of an artifact
    is reading it. An unauthorized caller learns only that access was denied.
    """
    await _require_read_access(request, resource_id=artifact_id)
    engine = get_database_engine()
    if engine is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=_NO_PERSISTENCE)

    record = await ArtifactRepository.get(engine, artifact_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artifact '{artifact_id}' not found",
        )
    await _require_read_access(request, record)
    await _require_not_deleted(request, record)
    return ArtifactResponse(**record)


@router.get(
    "/{artifact_id}/download",
    summary="Download the bytes of an artifact (§24.2)",
)
async def download_artifact(artifact_id: str, request: Request) -> Response:
    """Return the delivered file with its §24.2 ``mime_type`` and name (§19.3)."""
    await _require_read_access(request, resource_id=artifact_id)
    engine = get_database_engine()
    if engine is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=_NO_PERSISTENCE)

    record = await ArtifactRepository.get(engine, artifact_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artifact '{artifact_id}' not found",
        )
    await _require_read_access(request, record)
    # §18.2 / décision 0016 — un artefact supprimé n'est pas téléchargeable, et le
    # refus tombe **avant** toute lecture du stockage : connaître l'identifiant ne
    # suffit jamais.
    await _require_not_deleted(request, record)

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
    # §24.2 — l'empreinte annoncée décrit les octets **réellement servis**. Elle est
    # donc recalculée ici, à partir de `content`, et comparée à celle que le record
    # publie : des octets qui ne correspondent pas à l'empreinte publiée sont un
    # défaut d'intégrité, pas un téléchargement à servir sous un faux nom.
    integrity = _integrity_headers(content, record)

    # §24.3 — le dernier maillon de la chaîne est tracé : le téléchargement servi.
    # Best effort : une trace manquante est signalée dans le journal, mais elle ne
    # prive pas l'appelant autorisé du fichier qu'il vient de demander.
    await _record_delivery_event(engine, artifact_id, target="http_download")

    # La condition `If-None-Match` est évaluée sur l'empreinte des octets lus,
    # jamais sur celle du record : un objet corrompu ne peut donc pas produire un
    # « 304 Not Modified » pour un contenu qui a changé.
    if request.headers.get("if-none-match") in (integrity["ETag"], integrity["X-Checksum-Sha256"]):
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=integrity)

    return Response(
        content=content,
        media_type=str(record.get("mime_type") or "application/octet-stream"),
        headers={
            "Content-Disposition": f'attachment; filename="{file_name}"',
            **integrity,
        },
    )


def _integrity_headers(content: Any, record: Mapping[str, Any]) -> dict[str, str]:
    """Return the §24.2 integrity headers of *content*, verified against *record*.

    ``ETag`` and ``X-Checksum-Sha256`` carry the **same** digest, computed from
    the bytes that are about to be returned: a client that verifies either one
    verifies what it received. When the artifact record publishes a different
    digest, the bytes are not the delivered file any more — the call is refused
    with an explicit ``502`` instead of a header that would look fine.

    Raises:
        HTTPException: 502 when the stored bytes do not match the published
            digest.
    """
    digest = hashlib.sha256(content).hexdigest()
    published = str(record.get("sha256") or "").strip().lower()
    if published and published != digest:
        logger.warning(
            "artifact bytes do not match the published digest",
            artifact_id=record.get("artifact_id"),
            published_sha256=published,
            served_sha256=digest,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "The stored bytes do not match the digest published for this artifact: "
                "the file is refused rather than served under a wrong checksum (§24.2)."
            ),
        )
    # A strong ETag (quoted, byte-exact representation): the same content yields
    # the same ETag on every call, on every worker.
    return {"ETag": f'"{digest}"', "X-Checksum-Sha256": digest}


async def _record_delivery_event(engine: Any, artifact_id: str, *, target: str) -> dict[str, Any]:
    """Record one §24.3 delivery event; never fail the download because of it."""
    from app.storage.repositories.artifact_version_repository import (
        ArtifactDeliveryEventRepository,
    )

    try:
        return await ArtifactDeliveryEventRepository.record(
            engine, artifact_id, target=target
        )
    except Exception as exc:  # noqa: BLE001 - §25.2: reported, not hidden
        logger.warning(
            "artifact delivery event not recorded", artifact_id=artifact_id, error=str(exc)
        )
        return {"artifact_id": artifact_id, "target": target, "recorded": False}


@router.get(
    "/{artifact_id}/versions",
    response_model=ArtifactVersionList,
    summary="Version history of an artifact and the version currently delivered",
)
async def list_artifact_versions(artifact_id: str, request: Request) -> ArtifactVersionList:
    """Return every version of an artifact, oldest first, and the current one.

    §18.1 — the history is append-only: a version is never rewritten. An artifact
    delivered **before** this history existed has no version row; the response
    then reports the version the `artifacts` row carries and an empty history
    rather than inventing a past.
    """
    await _require_read_access(request, resource_id=artifact_id)
    engine = get_database_engine()
    if engine is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=_NO_PERSISTENCE)

    record = await ArtifactRepository.get(engine, artifact_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artifact '{artifact_id}' not found",
        )
    await _require_read_access(request, record)
    await _require_not_deleted(request, record)

    versions = await ArtifactVersionRepository.list_for_artifact(engine, artifact_id)
    return ArtifactVersionList(
        artifact_id=artifact_id,
        current_version=(versions[-1]["version"] if versions else record.get("version")),
        versions=[await _version_with_lineage(engine, artifact_id, row) for row in versions],
    )


@router.get(
    "/{artifact_id}/lineage",
    response_model=ArtifactLineageView,
    summary="Lineage and deliveries of an artifact: source → … → download",
)
async def get_artifact_lineage(artifact_id: str, request: Request) -> ArtifactLineageView:
    """Return the per-version lineage and every recorded delivery (§24.2/§24.3)."""
    await _require_read_access(request, resource_id=artifact_id)
    engine = get_database_engine()
    if engine is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=_NO_PERSISTENCE)

    record = await ArtifactRepository.get(engine, artifact_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artifact '{artifact_id}' not found",
        )
    await _require_read_access(request, record)
    await _require_not_deleted(request, record)

    versions = await ArtifactVersionRepository.list_for_artifact(engine, artifact_id)
    events = await ArtifactDeliveryEventRepository.list_for_artifact(engine, artifact_id)
    return ArtifactLineageView(
        artifact_id=artifact_id,
        versions=[await _version_with_lineage(engine, artifact_id, row) for row in versions],
        delivery_events=[ArtifactDeliveryEventResponse(**event) for event in events],
    )


async def _version_with_lineage(
    engine: Any, artifact_id: str, version_row: dict[str, Any]
) -> ArtifactVersionResponse:
    """Attach the lineage recorded for one version to its version row."""
    lineage = await ArtifactLineageRepository.get_for_version(
        engine, artifact_id, str(version_row["version"])
    )
    return ArtifactVersionResponse(
        **version_row,
        lineage=ArtifactLineageResponse(**lineage) if lineage else None,
    )
