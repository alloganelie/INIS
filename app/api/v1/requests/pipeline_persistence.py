"""Persistence helper for pipeline delivery findings per section 0.2, 12, 20, 27."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from app.domain.value_objects.ulid import ULID


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
        "timestamp": datetime.now(timezone.utc).isoformat(),
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
    try:
        async for session in get_session():
            now_dt = datetime.now(timezone.utc)
            stored_audit = await AuditWriter().write(audit_payload, session=session)
            await _insert_sources(session, sources, now_dt)
            inf_ids = await _insert_units(session, information_units, now_dt)
            await _insert_evidence(session, evidence, now_dt)
            await _insert_lineage(session, sources, inf_ids, step_results, delivery_status, request_id, now_dt)
            await session.commit()
            return True, [], stored_audit
    except Exception as exc:
        return (
            False,
            [f"persistence: db write degraded ({type(exc).__name__}: {exc})"],
            stored_audit,
        )
    return False, ["persistence: no session acquired"], fallback_audit


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
        await session.execute(
            text(
                """
                INSERT INTO sources (id, url, source_type, reliability_score, freshness, data_stage, created_at, updated_at)
                VALUES (:id, :url, :source_type, :reliability_score, NULL, :data_stage, :created_at, :updated_at)
                ON CONFLICT (id) DO UPDATE SET
                    updated_at = EXCLUDED.updated_at,
                    reliability_score = COALESCE(EXCLUDED.reliability_score, sources.reliability_score)
                """
            ),
            {
                "id": src_id,
                "url": src_url,
                "source_type": src_type,
                "reliability_score": rel_score,
                "data_stage": "derived" if src_type == "internal" else "raw",
                "created_at": now_dt,
                "updated_at": now_dt,
            },
        )


async def _insert_units(session: Any, information_units: list[dict[str, Any]], now_dt: datetime) -> list[str]:
    inf_ids: list[str] = []
    for unit in information_units:
        inf_id = unit.get("information_id") or ULID.new("INF_")
        inf_ids.append(inf_id)
        unit_source_id = unit.get("source_id") or "SRC_INTERNAL_PIPELINE"
        await session.execute(
            text(
                """
                INSERT INTO sources (id, url, source_type, data_stage, created_at, updated_at)
                VALUES (:id, :url, :source_type, :data_stage, :created_at, :updated_at)
                ON CONFLICT (id) DO NOTHING
                """
            ),
            {
                "id": unit_source_id,
                "url": f"internal://{unit_source_id}",
                "source_type": "internal",
                "data_stage": "derived",
                "created_at": now_dt,
                "updated_at": now_dt,
            },
        )
        content_payload = json.dumps(unit.get("content") or {})
        await session.execute(
            text(
                """
                INSERT INTO information_units (id, type, content, source_id, document_id, data_stage, created_at)
                VALUES (:id, :type, CAST(:content AS JSONB), :source_id, NULL, :data_stage, :created_at)
                ON CONFLICT (id) DO NOTHING
                """
            ),
            {
                "id": inf_id,
                "type": unit.get("type", "text"),
                "content": content_payload,
                "source_id": unit_source_id,
                "data_stage": unit.get("data_stage", "derived"),
                "created_at": now_dt,
            },
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
        await session.execute(
            text(
                """
                INSERT INTO evidence (evidence_id, information_id, source_id, document_id, quote, confidence, created_at)
                VALUES (:evidence_id, :information_id, :source_id, NULL, :quote, :confidence, :created_at)
                ON CONFLICT (evidence_id) DO NOTHING
                """
            ),
            {
                "evidence_id": ev_id,
                "information_id": ev.get("information_id"),
                "source_id": ev.get("source_id"),
                "quote": ev.get("excerpt") or ev.get("quote"),
                "confidence": conf_val,
                "created_at": now_dt,
            },
        )


async def _insert_lineage(
    session: Any,
    sources: list[dict[str, Any]],
    inf_ids: list[str],
    step_results: list[dict[str, Any]],
    delivery_status: str,
    request_id: str,
    now_dt: datetime,
) -> None:
    input_src_ids = [s.get("source_id") for s in sources if s.get("source_id")]
    if not (input_src_ids and inf_ids):
        return
    trf_id = ULID.new("TRF_")
    await session.execute(
        text(
            """
            INSERT INTO transformations (
                transformation_id, input_ids, output_ids, operator, tool,
                tool_version, parameters, timestamp, result, justification
            ) VALUES (
                :transformation_id, CAST(:input_ids AS JSONB), CAST(:output_ids AS JSONB),
                :operator, :tool, :tool_version, CAST(:parameters AS JSONB),
                :timestamp, :result, :justification
            )
            ON CONFLICT (transformation_id) DO NOTHING
            """
        ),
        {
            "transformation_id": trf_id,
            "input_ids": json.dumps(input_src_ids),
            "output_ids": json.dumps(inf_ids),
            "operator": "PipelineRunner",
            "tool": "PipelineRunner.run",
            "tool_version": "1.0.0",
            "parameters": json.dumps({"steps_executed": len(step_results)}),
            "timestamp": now_dt,
            "result": delivery_status,
            "justification": f"Synthesized research for {request_id}",
        },
    )
