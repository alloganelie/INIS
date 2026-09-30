"""Persistence helper for pipeline delivery findings per section 0.2, 12, 20, 27."""

from __future__ import annotations

import os
import time
from datetime import UTC, datetime
from typing import Any

from app.domain.value_objects.ulid import ULID
from app.storage.repositories.evidence_repository import evidence_table
from app.storage.repositories.information_unit_repository import information_units_table
from app.storage.repositories.source_repository import sources_table
from app.storage.repositories.table_repository import insert_rows
from app.storage.repositories.transformation_repository import TransformationRepository


async def persist_pipeline_delivery(
    request_id: str,
    objective: str,
    delivery_status: str,
    sources: list[dict[str, Any]],
    information_units: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    step_results: list[dict[str, Any]],
) -> tuple[bool, list[str], dict[str, Any]]:
    db_url = os.getenv("INIS_DATABASE_URL")
    fallback_audit = {
        "audit_event_id": ULID.new("AUD_"),
        "timestamp": datetime.now(UTC).isoformat(),
    }
    if not db_url:
        return (
            False,
            ["persistence: in-memory only (INIS_DATABASE_URL not set)"],
            fallback_audit,
        )

    from app.governance.audit.audit_writer import AuditWriter
    from app.storage.database.session import ensure_session_maker, get_session

    if not ensure_session_maker():
        return (
            False,
            ["persistence: in-memory only (INIS_DATABASE_URL not set)"],
            fallback_audit,
        )

    audit_payload = {
        "actor_type": "pipeline",
        "actor_id": "agent:pipeline_runner",
        "action": "delivery",
        "resource_type": "request",
        "resource_id": request_id,
        "request_id": request_id,
        "result": "success" if delivery_status == "completed" else "degraded",
        "reason": f"Delivery synthesized for '{objective[:80]}'",
    }
    stored_audit: dict[str, Any] = fallback_audit
    started = time.perf_counter()
    try:
        async for session in get_session():
            now_dt = datetime.now(UTC)
            stored_audit = await AuditWriter().write(audit_payload, session=session)
            await _insert_sources(session, sources, now_dt)
            await _insert_units(session, information_units, now_dt)
            await _insert_evidence(session, evidence, now_dt)
            await session.commit()
            _observe_postgres_latency(started)
            return True, [], stored_audit
    except Exception as exc:  # noqa: BLE001 - §25.2: a degraded write is reported, not raised
        _observe_postgres_latency(started)
        return (
            False,
            [f"persistence: db write degraded ({type(exc).__name__}: {exc})"],
            stored_audit,
        )
    return False, ["persistence: no session acquired"], fallback_audit


def _observe_postgres_latency(started: float) -> None:
    """Feed the §34 ``postgres_latency`` histogram (milliseconds)."""
    try:
        from app.observability.metrics import observe_value

        observe_value("postgres_latency", (time.perf_counter() - started) * 1000.0)
    except Exception:  # noqa: BLE001, S110 - observability never breaks persistence
        pass


async def _insert_sources(session: Any, sources: list[dict[str, Any]], now_dt: datetime) -> None:
    for src in sources:
        src_id = src.get("source_id") or ULID.new("SRC_")
        src_url = src.get("url") or f"internal://{src_id}"
        src_type = src.get("source_type") or "web"
        rel_score = src.get("reliability_score")
        try:
            rel_score = float(rel_score) if rel_score is not None else None
        except (TypeError, ValueError):
            rel_score = None
        # The row is built here, the *definition* of the table lives only in
        # ``SourceRepository``: the raw ``INSERT`` that used to be typed in this
        # module was a second schema, and it drifted (§27, L6.1).
        await insert_rows(
            session,
            sources_table,
            [
                {
                    "id": src_id,
                    "url": src_url,
                    "source_type": src_type,
                    "reliability_score": rel_score,
                    "freshness": None,
                    "data_stage": "derived" if src_type == "internal" else "raw",
                    "created_at": now_dt,
                    "updated_at": now_dt,
                }
            ],
            conflict_columns=("id",),
            update_columns=("updated_at",),
            coalesce_columns=("reliability_score",),
        )


async def _insert_units(session: Any, information_units: list[dict[str, Any]], now_dt: datetime) -> list[str]:
    inf_ids: list[str] = []
    for unit in information_units:
        inf_id = unit.get("information_id") or ULID.new("INF_")
        inf_ids.append(inf_id)
        unit_source_id = unit.get("source_id") or "SRC_INTERNAL_PIPELINE"
        await insert_rows(
            session,
            sources_table,
            [
                {
                    "id": unit_source_id,
                    "url": f"internal://{unit_source_id}",
                    "source_type": "internal",
                    "data_stage": "derived",
                    "created_at": now_dt,
                    "updated_at": now_dt,
                }
            ],
            conflict_columns=("id",),
        )
        content_payload = unit.get("content") or {}
        # §11 — the persisted row mirrors the delivered unit, so the provenance
        # survives a restart and /v1/information/{id} can still explain where
        # the information came from.
        await insert_rows(
            session,
            information_units_table,
            [
                {
                    "id": inf_id,
                    "type": unit.get("type", "text"),
                    "content": content_payload,
                    "source_id": unit_source_id,
                    "document_id": unit.get("document_id"),
                    "dataset_id": unit.get("dataset_id"),
                    "location": unit.get("location"),
                    "data_stage": unit.get("data_stage", "derived"),
                    "raw_reference": unit.get("raw_reference") or {},
                    "context": unit.get("context") or {},
                    "language": unit.get("language"),
                    "epistemic_status": unit.get("epistemic_status") or "factual",
                    "provenance": unit.get("provenance") or {},
                    "created_at": now_dt,
                    "updated_at": now_dt,
                }
            ],
            conflict_columns=("id",),
        )
    return inf_ids


async def _insert_evidence(session: Any, evidence: list[dict[str, Any]], now_dt: datetime) -> None:
    for ev in evidence:
        ev_id = ev.get("evidence_id") or ULID.new("EVID_")
        conf = ev.get("strength") if ev.get("strength") is not None else ev.get("confidence")
        try:
            conf_val = float(conf) if conf is not None else None
        except (TypeError, ValueError):
            conf_val = None
        await insert_rows(
            session,
            evidence_table,
            [
                {
                    "evidence_id": ev_id,
                    "information_id": ev.get("information_id"),
                    "source_id": ev.get("source_id"),
                    "document_id": ev.get("document_id"),
                    "claim_id": ev.get("claim_id"),
                    "transformation_id": ev.get("transformation_id"),
                    "quote": ev.get("excerpt") or ev.get("quote"),
                    "confidence": conf_val,
                    # §14.2 — strength is the evidence's own signal; it used to be
                    # omitted, so every persisted evidence came back with the
                    # neutral default instead of what the run measured.
                    "strength": conf_val,
                    "epistemic_status": ev.get("epistemic_status") or "fact",
                    "provenance": ev.get("provenance") or {},
                    "created_at": now_dt,
                }
            ],
            conflict_columns=("evidence_id",),
        )


async def persist_transformations(
    transformations: list[dict[str, Any]],
    *,
    request_id: str,
) -> bool:
    """Write one §12.1 row per transformation a run executed.

    Args:
        transformations: The rows built by
            :func:`app.knowledge.provenance.stage_transformations.build_transformations`.
        request_id: The request they belong to (used for the log/limitation text).

    Returns:
        ``True`` when they were written, ``False`` when no database is
        configured. A write that fails never raises: the delivery is already
        built and must not be lost because its lineage could not be stored.

    Replaces the single generic ``TRF_`` row this module used to write for every
    run, whatever it had actually done (§12.1, C11).
    """
    if not transformations:
        return True
    from app.storage.database.session import ensure_session_maker, get_session

    if not ensure_session_maker():
        return False
    try:
        async for session in get_session():
            await TransformationRepository.insert_many_in(session, transformations)
            await session.commit()
            return True
    except Exception:  # noqa: BLE001 - §25.2: the delivery outlives its lineage
        return False
    return False
