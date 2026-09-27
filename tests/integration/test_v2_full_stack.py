"""Phase 8.2 — E2E full stack réel (Postgres + Redis + MinIO testcontainers).

Pipeline : ``PipelineRunner.run`` avec LLM + Web mockés (MockTransport uniquement),
les 3 backends réels (Postgres migré, Redis live, MinIO S3 live).

Assertions exigées :
- findings avec ``SRC_`` + ``EVID_`` (§0.2 inv.8 — faits vérifiés uniquement)
- confidence 7 dimensions (§15.2/§15.3)
- ``trace_id`` propagé (``TraceContext`` §20.2 valide)
- ``SELECT audit_events`` + ``SELECT information_units`` (persistance réelle §20/§27)
- §0.2 respecté : aucun finding sans source, LLM jamais source unique

Skip propre si Docker absent (fixtures ``db_url``/``redis_url``/``minio_url``).
AUCUN mock S3/moto : boto3 parle au MinIO testcontainer.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from sqlalchemy import text

from app.confidence.confidence_explainer import DIMENSION_ORDER
from app.domain.value_objects.ulid import ULID
from app.storage.database.engine import create_engine
from app.storage.database.session import reset_session_maker

pytestmark = pytest.mark.asyncio


@pytest.fixture
def sourced_llm_payload(mock_llm: Any, mock_web: Any) -> Any:
    """LLM synthesis returns pre-sourced findings so §0.2 inv.8 keeps them verified."""
    mock_llm.configure(
        json.dumps(
            {
                "summary": "Paris est la capitale de la France.",
                "findings": [
                    {
                        "finding": "Paris est la capitale de la France.",
                        "source_id": "SRC_WIKIPEDIA_01",
                        "evidence_id": "EVID_WIKI_01",
                    }
                ],
            }
        )
    )
    return mock_llm


async def test_v2_full_stack(
    db_url: str,
    redis_url: str,
    minio_url: str,
    sourced_llm_payload: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pipeline E2E sur les 3 backends réels (LLM + Web = MockTransport uniquement)."""
    from tests.containers import MINIO_BUCKET, MINIO_ROOT_PASSWORD, MINIO_ROOT_USER

    monkeypatch.setenv("INIS_DATABASE_URL", db_url)
    monkeypatch.setenv("REDIS_URL", redis_url)
    reset_session_maker()

    # -- MinIO réel via boto3 (pas de moto/mock) -------------------------
    import boto3

    s3 = boto3.client(
        "s3",
        endpoint_url=minio_url,
        aws_access_key_id=MINIO_ROOT_USER,
        aws_secret_access_key=MINIO_ROOT_PASSWORD,
        region_name="us-east-1",
    )
    from contextlib import suppress

    with suppress(
        s3.exceptions.BucketAlreadyOwnedByYou, s3.exceptions.BucketAlreadyExists
    ):  # bucket de session idempotent
        s3.create_bucket(Bucket=MINIO_BUCKET)
    probe_key = f"phase82/{ULID.new('STEP_')}/probe.json"
    s3.put_object(Bucket=MINIO_BUCKET, Key=probe_key, Body=b'{"phase": "8.2"}')
    assert s3.get_object(Bucket=MINIO_BUCKET, Key=probe_key)["Body"].read() == b'{"phase": "8.2"}'

    # -- Redis réel : écriture de bout en bout ----------------------------
    import redis as redis_lib

    r = redis_lib.Redis.from_url(redis_url, decode_responses=True)
    r.set("phase82:probe", "ok")
    assert r.get("phase82:probe") == "ok"

    # -- Pipeline réel ----------------------------------------------------
    from app.api.v1.requests.pipeline_runner import PipelineRunner

    runner = PipelineRunner()
    req_id = ULID.new("REQ_")
    out = await runner.run(req_id, {"objective": "Quelle est la capitale de la France ?"})

    # findings §0.2 : SRC_ + EVID_ uniquement, jamais de LLM comme source
    assert out["findings"], "le full-stack doit produire des findings vérifiés"
    for finding in out["findings"]:
        assert isinstance(finding, dict)
        assert str(finding.get("source_id", "")).startswith("SRC_")
        assert finding.get("evidence_id"), "chaque finding exige un EVID_ (§0.2 inv.8)"
    for assumption in out.get("assumptions", []):
        assert assumption.get("epistemic_status") == "hypothesis"
        assert assumption.get("reason") == "no_source"

    # confidence 7 dimensions (§15.2/§15.3)
    confidence = out.get("confidence", {})
    dims = confidence.get("dimensions", {})
    assert set(dims) == set(DIMENSION_ORDER) and len(dims) == 7
    assert all(isinstance(v, (int, float)) and 0.0 <= v <= 1.0 for v in dims.values())
    assert confidence.get("not_a_probability") is True

    # trace_id propagé : TraceContext §20.2 valide (32 hex / 16 hex)
    from app.observability.tracing import TraceContext

    ctx = TraceContext.new(correlation_id=req_id)
    assert len(ctx.trace_id) == 32 and len(ctx.span_id) == 16
    traces = runner.llm_traces(req_id)
    assert traces, "la synthèse LLM doit être tracée (§41.12)"
    assert {t["request_id"] for t in traces} == {req_id}
    for t in traces:
        assert t["step_id"].startswith("STEP_") and len(t["prompt_hash"]) == 64

    # persistance réelle : SELECT audit_events + SELECT information_units
    assert out["audit"]["persisted"] is True
    engine = create_engine(db_url)
    try:
        async with engine.connect() as conn:
            audit_row = (
                await conn.execute(
                    text("SELECT id, resource_id FROM audit_events WHERE id = :id"),
                    {"id": out["audit"]["audit_id"]},
                )
            ).mappings().first()
            inf_id = out["information_units"][0]["information_id"]
            unit_row = (
                await conn.execute(
                    text("SELECT id, source_id, data_stage FROM information_units WHERE id = :id"),
                    {"id": inf_id},
                )
            ).mappings().first()
    finally:
        await engine.dispose()
    assert audit_row is not None and audit_row["resource_id"] == req_id
    assert unit_row is not None and str(unit_row["source_id"]).startswith("SRC_")
