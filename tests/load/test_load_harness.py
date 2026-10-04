"""§41.13 — le harnais de charge, et la preuve qu'il mesure le chemin réel.

Le plan demandait un harnais sur le chemin complet
``upload → ingestion → livraison → download``, exécuté en CI manuelle avec des
résultats archivés. Ce fichier prouve trois choses distinctes :

1. **la structure** : configuration validée, jeu de données déterministe,
   percentiles et contrôles de seuils calculés par des règles explicites ;
2. **le chemin réel** : le harnais est exécuté contre un **vrai serveur uvicorn**
   (socket TCP), avec la vraie base PostgreSQL et le vrai stockage objet — les six
   étapes passent par les routes de l'application, et l'artefact téléchargé est
   vérifié par son ``sha256`` ;
3. **la détection des échecs** : un parcours cassé et un seuil dépassé donnent
   ``FAIL`` — jamais un succès déclaré.

Ce que ce fichier ne fait pas : il n'exécute pas la campagne de charge du plan
dans la suite normale — c'est l'objet de ``tests/load/run_load.py`` et du
workflow manuel, dont les résultats s'archivent.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.main import app
from tests.load.harness import (
    BENCHMARK_DATASET_NAME,
    HARNESS_VERSION,
    SCENARIO_STEPS,
    THRESHOLD_METRICS,
    THROUGHPUT_KEY,
    IterationOutcome,
    LoadConfig,
    StepOutcome,
    benchmark_dataset,
    evaluate_checks,
    percentile,
    run_load,
    summarize,
    write_result,
)


def check_for(checks: list[dict[str, Any]], name: str) -> dict[str, Any]:
    """Return the named control of a campaign (there is exactly one per metric)."""
    return next(check for check in checks if check["name"] == name)


def _outcomes(*, ok: int, failed: int) -> list[IterationOutcome]:
    """Build synthetic outcomes with known durations (pure aggregation tests)."""
    good = [
        IterationOutcome(
            steps=[
                StepOutcome(name, 0.010 * (index + 1), True) for name in SCENARIO_STEPS
            ],
            ok=True,
        )
        for index in range(ok)
    ]
    bad = [
        IterationOutcome(
            steps=[StepOutcome("ingest_and_run", 0.002, False, "HTTP 500")],
            ok=False,
            error="ingest_and_run: HTTP 500",
        )
        for _ in range(failed)
    ]
    return [*good, *bad]


class TestConfiguration:
    """§41.13 — la configuration du harnais ne contient aucun seuil."""

    def test_the_defaults_are_a_runnable_campaign(self) -> None:
        config = LoadConfig()

        assert config.requests >= 1
        assert config.concurrency <= config.requests
        assert config.measurement_scope == "local"

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"requests": 0},
            {"concurrency": 0},
            {"requests": 2, "concurrency": 3},
            {"timeout_s": 0},
            {"dataset_rows": 0},
            {"measurement_scope": "production"},
        ],
    )
    def test_an_unusable_configuration_is_refused(self, kwargs: dict[str, Any]) -> None:
        with pytest.raises(ValueError):
            LoadConfig(**kwargs)

    @pytest.mark.parametrize(
        "required",
        [
            ("post", "/v1/requests"),
            ("post", "/v1/requests/{request_id}/documents"),
            ("get", "/v1/requests/{id}"),
            ("get", "/v1/artifacts"),
            ("get", "/v1/artifacts/{artifact_id}/download"),
            ("get", "/v1/metrics"),
        ],
    )
    def test_every_step_uses_a_route_the_application_exposes(
        self, required: tuple[str, str]
    ) -> None:
        """Les routes du scénario existent réellement (§32/§41.15) : aucune n'est inventée."""
        method, path = required
        exposed = app.openapi()["paths"]

        assert path in exposed, f"{path} n'est pas exposée par l'application"
        assert method in exposed[path], f"{method.upper()} {path} n'est pas exposée"


class TestMetrics:
    """§41.13 — les mesures publiées sont calculées par des règles explicites."""

    def test_the_benchmark_dataset_is_deterministic(self) -> None:
        first = benchmark_dataset(3)

        assert first == benchmark_dataset(3), "deux campagnes téléversent le même document"
        assert first != benchmark_dataset(4)
        lines = first.decode().strip().splitlines()
        assert lines[0] == "row_id,label,amount,unit"
        assert len(lines) == 4, "l'en-tête + une ligne par rangée"
        assert BENCHMARK_DATASET_NAME in lines[1], "la donnée dit qu'elle est un benchmark"

    def test_percentiles_are_nearest_rank_and_empty_safe(self) -> None:
        samples = [4.0, 1.0, 3.0, 2.0]

        assert percentile(samples, 0.50) == 2.0
        assert percentile(samples, 0.95) == 4.0
        assert percentile(samples, 0.99) == 4.0
        assert percentile([], 0.95) is None

    def test_the_summary_counts_successes_errors_and_throughput(self) -> None:
        config = LoadConfig(requests=3, concurrency=1)

        summary = summarize(_outcomes(ok=2, failed=1), 2.0, config=config)

        assert summary["requests"] == 3
        assert summary["ok"] == 2
        assert summary["errors"] == 1
        assert summary["error_rate"] == pytest.approx(1 / 3)
        assert summary["throughput_rps"] == pytest.approx(1.0), "2 parcours réussis en 2 s"
        assert summary["steps"]["ingest_and_run"]["failed"] == 1
        assert summary["steps"]["download_artifact"]["measured"] == 2
        assert summary["failures"] == ["ingest_and_run: HTTP 500"]

    def test_a_broken_path_can_never_pass(self) -> None:
        """Aucun succès déclaré quand un parcours a échoué, quel que soit le seuil."""
        summary = summarize(_outcomes(ok=1, failed=1), 1.0, config=LoadConfig())

        checks = evaluate_checks(
            summary,
            {THROUGHPUT_KEY: 10_000.0},
            {"vector_search_latency": {"observed": 1, "p99": 1.0}},
            scope="staging",
        )

        assert checks[0]["status"] == "fail"
        assert checks[0]["reason"] == "au moins un parcours complet a échoué"


class TestThresholds:
    """§41.13 — les seuils sont ceux du système, et ils ne sont pas inventés."""

    def test_a_local_campaign_publishes_but_does_not_apply_staging_targets(self) -> None:
        summary = summarize(_outcomes(ok=2, failed=0), 1.0, config=LoadConfig())
        benchmarks = {THROUGHPUT_KEY: 50.0, "vector_search_latency_p99_ms": 15.0}

        checks = evaluate_checks(
            summary,
            benchmarks,
            {"vector_search_latency": {"observed": 4, "p99": 40.0}},
            scope="local",
        )

        assert all(check["status"] == "not_measured" for check in checks)
        throughput = check_for(checks, "throughput_requests_per_second")
        assert "staging" in str(throughput["reason"])
        assert throughput["threshold"] == 50.0, "le seuil exposé est publié tel quel"
        assert throughput["observed"] is not None, "la mesure est publiée à côté du seuil"

    def test_a_staging_campaign_applies_the_exposed_values(self) -> None:
        summary = summarize(_outcomes(ok=4, failed=0), 1.0, config=LoadConfig())
        benchmarks = {THROUGHPUT_KEY: 50.0, "vector_search_latency_p99_ms": 15.0}

        fast = evaluate_checks(
            summary,
            benchmarks,
            {"vector_search_latency": {"observed": 4, "p99": 9.0}},
            scope="staging",
        )
        slow = evaluate_checks(
            summary,
            benchmarks,
            {"vector_search_latency": {"observed": 4, "p99": 40.0}},
            scope="staging",
        )

        assert fast[0]["status"] == "fail", "4 req/s observés < 50 req/s exposés"
        assert fast[1]["status"] == "pass", "9 ms < 15 ms"
        assert slow[1]["status"] == "fail", "40 ms > 15 ms"

    def test_the_direction_of_the_comparison_follows_the_metric(self) -> None:
        """Un débit élevé est une réussite, une latence élevée un dépassement."""
        fast = summarize(_outcomes(ok=100, failed=0), 1.0, config=LoadConfig())

        checks = evaluate_checks(fast, {THROUGHPUT_KEY: 50.0}, {}, scope="staging")

        assert checks[0]["status"] == "pass", "100 req/s >= 50 req/s"

    def test_a_threshold_without_samples_is_never_a_pass(self) -> None:
        summary = summarize(_outcomes(ok=1, failed=0), 1.0, config=LoadConfig())

        checks = evaluate_checks(
            summary,
            {THROUGHPUT_KEY: 50.0},
            {"llm_latency": {"observed": 0, "p99": None}},
            scope="staging",
        )

        llm = check_for(checks, "llm_latency")
        assert llm["status"] == "not_measured"
        assert llm["observed"] is None
        assert "aucun échantillon" in str(llm["reason"])
        assert llm["threshold_key"] in THRESHOLD_METRICS, "le nom vient du §41.13"


class TestArchive:
    """§41.13 / plan — un résultat s'archive de façon déterministe."""

    def test_the_record_name_and_body_are_deterministic(self, tmp_path: Path) -> None:
        record = {
            "harness_version": HARNESS_VERSION,
            "git": {"commit": "abc1234", "branch": "feat/conformance-v1", "dirty": False},
            "status": "MEASURED",
            "metrics": {"requests": 1},
        }

        path = write_result(record, tmp_path)

        assert "abc1234" in path.name and path.name.endswith("-MEASURED.json")
        written = path.read_text(encoding="utf-8")
        assert written == json.dumps(
            json.loads(written), indent=2, sort_keys=True, ensure_ascii=False
        ) + "\n", "l'archive est triée : deux campagnes se comparent ligne à ligne"


@pytest.fixture
def live_stack(db_url: str, minio_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Wire the application to the real PostgreSQL and the real object store."""
    from contextlib import suppress

    import boto3

    from app.storage.database.engine import set_default_engine
    from app.storage.database.session import reset_session_maker
    from tests.containers import MINIO_BUCKET, MINIO_ROOT_PASSWORD, MINIO_ROOT_USER

    raw = boto3.client(
        "s3",
        endpoint_url=minio_url,
        aws_access_key_id=MINIO_ROOT_USER,
        aws_secret_access_key=MINIO_ROOT_PASSWORD,
        region_name="us-east-1",
    )
    with suppress(
        raw.exceptions.BucketAlreadyOwnedByYou, raw.exceptions.BucketAlreadyExists
    ):
        raw.create_bucket(Bucket=MINIO_BUCKET)

    monkeypatch.setenv("INIS_DATABASE_URL", db_url)
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("S3_ENDPOINT", minio_url)
    monkeypatch.setenv("S3_ACCESS_KEY", MINIO_ROOT_USER)
    monkeypatch.setenv("S3_SECRET_KEY", MINIO_ROOT_PASSWORD)
    monkeypatch.setenv("S3_BUCKET", MINIO_BUCKET)
    monkeypatch.setenv("S3_USE_SSL", "false")
    # §41.14 — un moteur par boucle : la campagne ouvre la sienne.
    monkeypatch.setenv("INIS_NULL_POOL", "1")
    set_default_engine(None)
    reset_session_maker()


@asynccontextmanager
async def _live_server() -> AsyncIterator[str]:
    """Serve the real application over a real TCP socket (uvicorn, port aléatoire)."""
    import uvicorn

    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning")
    )
    task = asyncio.create_task(server.serve())
    try:
        for _ in range(200):
            if server.started:
                break
            await asyncio.sleep(0.05)
        assert server.started, "uvicorn n'a pas démarré"
        port = server.servers[0].sockets[0].getsockname()[1]
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        await task


async def _respond(response: httpx.Response) -> httpx.Response:
    """Return *response* from a coroutine (step helper for the offline proofs)."""
    return response


@pytest.mark.asyncio
async def test_the_harness_drives_the_real_path_over_http(
    live_stack: None, mock_llm: Any, tmp_path: Path
) -> None:
    """§41.13 — le parcours réel est mesuré de bout en bout, sur un vrai serveur.

    Six étapes par itération, toutes sur les routes de l'application, avec la
    vraie base et le vrai stockage : deux parcours complets, aucune erreur, et
    l'archive du résultat écrite sur disque.
    """
    mock_llm.configure(json.dumps({"summary": "charge §41.13", "findings": []}))

    async with _live_server() as base_url:
        result = await run_load(
            LoadConfig(
                base_url=base_url,
                requests=2,
                concurrency=2,
                dataset_rows=5,
                timeout_s=180.0,
                notes=(
                    (
                        "LLM simulé par la suite (`mock_llm`) : le chemin HTTP, la base et "
                        "le stockage objet sont réels"
                    ),
                ),
            )
        )

    summary = result.summary
    assert summary["ok"] == 2, summary["failures"]
    assert summary["errors"] == 0, summary["failures"]
    for name in SCENARIO_STEPS:
        assert summary["steps"][name]["measured"] == 2, name
        assert summary["steps"][name]["failed"] == 0, name
    assert summary["throughput_rps"] and summary["throughput_rps"] > 0

    record = result.record
    assert result.status == "MEASURED", "portée locale : les cibles de staging ne s'appliquent pas"
    assert record["thresholds"]["values"], "les seuils exposés par /v1/metrics sont publiés"
    assert record["thresholds"]["values"]["max_plan_steps"] > 0
    assert record["config"]["measurement_scope"] == "local"
    assert record["scenario"] == list(SCENARIO_STEPS)
    assert any("staging" in line for line in record["limitations"])
    assert write_result(record, tmp_path).is_file()


@pytest.mark.asyncio
async def test_a_campaign_against_an_unreachable_server_is_a_failure() -> None:
    """Contre-épreuve — parcours cassé : la campagne se déclare en échec.

    Aucun serveur à l'adresse visée : la première étape échoue, la cause est
    enregistrée, et rien ne peut être compté comme un succès.
    """
    result = await run_load(
        LoadConfig(base_url="http://127.0.0.1:9", requests=1, concurrency=1, timeout_s=2.0)
    )

    assert result.summary["ok"] == 0
    assert result.summary["errors"] == 1
    assert result.record["status"] == "FAIL"
    assert result.summary["failures"], "la cause de l'échec est enregistrée"
    assert result.record["checks"][0]["reason"] == "au moins un parcours complet a échoué"


@pytest.mark.asyncio
async def test_an_http_error_fails_the_step_it_happened_in() -> None:
    """Contre-épreuve — une réponse 500 n'est jamais comptée comme une étape réussie."""
    from tests.load.harness import IterationFailed, _timed

    outcomes: list[StepOutcome] = []
    response = httpx.Response(500, request=httpx.Request("POST", "http://inis/v1/requests"))

    with pytest.raises(IterationFailed, match="HTTP 500"):
        await _timed(outcomes, "submit_request", _respond(response))

    assert outcomes[0].ok is False
    assert outcomes[0].detail == "HTTP 500"


@pytest.mark.asyncio
async def test_a_staging_campaign_fails_on_the_exposed_throughput(
    live_stack: None, mock_llm: Any
) -> None:
    """Contre-épreuve — seuil dépassé : la cible exposée est appliquée puis détectée.

    Le parcours réussit, mais le débit d'un poste de travail reste sous la cible
    de staging publiée par ``/v1/metrics`` : la campagne est en ``FAIL``, et le
    contrôle nomme le seuil **exposé** (jamais un chiffre inventé par le harnais).
    """
    mock_llm.configure(json.dumps({"summary": "charge §41.13", "findings": []}))

    async with _live_server() as base_url:
        result = await run_load(
            LoadConfig(
                base_url=base_url,
                requests=1,
                concurrency=1,
                dataset_rows=5,
                timeout_s=180.0,
                measurement_scope="staging",
            )
        )

    assert result.summary["ok"] == 1, "le parcours complet a réussi"
    assert result.record["status"] == "FAIL", "…mais le seuil exposé est dépassé"
    throughput = check_for(result.record["checks"], "throughput_requests_per_second")
    assert throughput["threshold"] == 50.0, "le seuil vient de /v1/metrics → benchmarks"
    assert throughput["observed"] < throughput["threshold"]
    assert throughput["status"] == "fail"
