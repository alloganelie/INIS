"""§41.13 — harnais de charge sur le chemin **réel** d'une requête INIS.

Ce que §41.13 demande (spec, l. 2140-2157) : huit benchmarks **nommés** —
débit, unités par requête, p99 vectoriel/PostgreSQL/AMQP/LLM, garde-fous de plan
et de concurrence — « **documentés, mesurés en environnement de staging et
exposés dans `/v1/metrics`** ». La spec **ne fixe aucun chiffre** : les valeurs
sont celles du dépôt, exposées par `GET /v1/metrics → benchmarks`
(`app/api/v1/system/metrics_router.py` + `app/planning/limits.py`). Ce module les
lit **là** au lieu de les réinventer, et compare aux mesures qu'il observe.

Le harnais mesure le **système réel** : les six étapes ci-dessous passent par les
routes HTTP de l'application, avec la vraie base, le vrai stockage objet et le
vrai pipeline. Rien n'est simulé côté INIS ; ce qui peut l'être à l'extérieur
(fournisseur LLM, fournisseur de recherche) est **déclaré** par l'appelant dans
``LoadConfig.notes`` et documenté dans ``docs/performance_tuning.md``.

Une itération = une « requête » du benchmark :

    1. POST /v1/requests                       → identifiant (support du téléversement)
    2. POST /v1/requests/{id}/documents        → le jeu de données est **téléversé**
    3. POST /v1/requests (source_ref=s3://…)   → **ingestion** avant planification
    4. GET  /v1/requests/{id}                  → attente de l'état terminal (livraison)
    5. GET  /v1/artifacts?request_id=…         → l'artefact demandé (§24.2)
    6. GET  /v1/artifacts/{aid}/download       → octets + **sha256 vérifié**

Les métriques de composant (§41.13 : p99 vectoriel, PostgreSQL, AMQP, LLM) sont
lues dans ``GET /v1/metrics`` **avant et après** la charge : elles sont observées
**par le système lui-même** pendant le run, jamais rejouées par le harnais.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import platform
import subprocess
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from app.core.statuses import OUTPUT_STATUSES, PIPELINE_SUCCESS_STATUS

__all__ = [
    "BENCHMARK_DATASET_NAME",
    "HARNESS_VERSION",
    "LoadConfig",
    "LoadResult",
    "benchmark_dataset",
    "evaluate_checks",
    "percentile",
    "run_load",
    "summarize",
    "write_result",
]

#: Version of the whole harness **and** of its result schema. A record that does
#: not carry the same number was produced by another implementation, so two runs
#: are only comparable when this field matches.
HARNESS_VERSION = 1

#: §41.13 — nom du jeu de données téléversé pendant la charge. Le nom dit ce que
#: le fichier est : une donnée de benchmark, jamais une donnée client.
BENCHMARK_DATASET_NAME = "benchmark_dataset.csv"

#: `LoadConfig` et le résultat n'ont pas de secret : ce sont des entiers, des
#: durées, des noms de route et des identifiants publics (§0.3).


@dataclass(frozen=True)
class LoadConfig:
    """Configuration d'une campagne de charge (§41.13).

    Aucune valeur de cette classe n'est un seuil : la taille du jeu de données et
    le nombre de requêtes sont les **paramètres du harness** choisis par
    l'opérateur (ou par la CI manuelle), pas une exigence contractuelle — §41.13
    ne fixe ni volume ni concurrence.
    """

    #: Racine de l'API à charger (ignorée quand ``app`` est fourni).
    base_url: str = "http://127.0.0.1:8000"
    #: Nombre d'itérations complètes (une itération = le parcours entier).
    requests: int = 5
    #: Itérations menées en parallèle.
    concurrency: int = 2
    #: Délai maximal d'un appel HTTP.
    timeout_s: float = 60.0
    #: Intervalle d'interrogation de l'état de la requête.
    poll_interval_s: float = 0.5
    #: Lignes du CSV téléversé (donnée de benchmark, déterministe).
    dataset_rows: int = 25
    #: Format d'artefact demandé (``required_output.format``).
    required_format: str = "csv"
    #: Portée de la mesure : ``local`` (poste de travail, CI) ou ``staging``.
    #: §41.13 exige des seuils « mesurés en environnement de staging » : une
    #: campagne locale **publie** les seuils exposés mais ne s'y compare pas
    #: (sinon on transformerait une cible de staging en exigence de poste de
    #: travail). En portée ``staging``, la comparaison est appliquée.
    measurement_scope: str = "local"
    #: Application ASGI à charger **en process** au lieu du réseau (utile en
    #: test : mêmes routes, même pipeline, sans socket). ``None`` = vraie URL.
    app: Any | None = None
    #: Ce que l'appelant a neutralisé ou impose (``LLM_API_KEY`` absent, etc.).
    #: Publié tel quel dans le résultat : une mesure sans son contexte est un
    #: chiffre qu'on ne peut pas comparer.
    notes: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.requests < 1:
            raise ValueError("requests must be >= 1")
        if self.concurrency < 1:
            raise ValueError("concurrency must be >= 1")
        if self.concurrency > self.requests:
            raise ValueError("concurrency must be <= requests")
        if self.timeout_s <= 0:
            raise ValueError("timeout_s must be > 0")
        if self.dataset_rows < 1:
            raise ValueError("dataset_rows must be >= 1")
        if self.measurement_scope not in ("local", "staging"):
            raise ValueError("measurement_scope must be 'local' or 'staging'")
        if not self.base_url and self.app is None:
            raise ValueError("base_url or app is required")


def benchmark_dataset(rows: int) -> bytes:
    """Return the deterministic CSV uploaded by the harness.

    Le contenu est **fixe** (mêmes octets pour un même nombre de lignes) : deux
    campagnes téléversent le même document, donc la même empreinte, donc la même
    ingestion — la mesure n'est pas bruitée par une donnée différente à chaque
    fois.
    """
    header = "row_id,label,amount,unit"
    body = "\n".join(
        f"{index},{BENCHMARK_DATASET_NAME}-{index:04d},{index * 3}.5,kg"
        for index in range(1, rows + 1)
    )
    return f"{header}\n{body}\n".encode()


#: Libellés des six étapes du parcours, dans l'ordre contractuel. Ils nomment les
#: routes réellement appelées : le résultat d'une campagne doit dire **quoi** a
#: été mesuré, pas seulement combien de temps cela a pris.
SCENARIO_STEPS: tuple[str, ...] = (
    "submit_request",
    "upload_dataset",
    "ingest_and_run",
    "await_delivery",
    "list_artifacts",
    "download_artifact",
)

#: §1.3 — états d'un run qui **livrent** une réponse complète : au-delà, le
#: harnais peut chercher l'artefact de la requête.
TERMINAL_STATUSES: tuple[str, ...] = (*OUTPUT_STATUSES, PIPELINE_SUCCESS_STATUS)


class IterationFailed(RuntimeError):
    """Une étape du parcours a échoué : l'itération est comptée en **erreur**."""


@dataclass
class StepOutcome:
    """Une étape mesurée d'une itération."""

    name: str
    seconds: float
    ok: bool
    detail: str | None = None


@dataclass
class IterationOutcome:
    """Une itération complète (ou interrompue) du parcours."""

    steps: list[StepOutcome]
    ok: bool
    error: str | None = None
    request_id: str | None = None
    artifact_id: str | None = None
    status: str | None = None
    digest_verified: bool = False


async def _timed(outcomes: list[StepOutcome], name: str, awaitable: Any) -> httpx.Response:
    """Await *awaitable*, record its duration and fail the step on an HTTP error.

    Une réponse ``>= 400`` n'est **pas** un succès : elle est enregistrée comme un
    échec d'étape (avec son code) et interrompt l'itération — c'est ce qui empêche
    le harnais de déclarer une campagne réussie sur un parcours cassé.
    """
    started = time.perf_counter()
    try:
        response = await awaitable
    except Exception as exc:
        outcomes.append(
            StepOutcome(name, time.perf_counter() - started, False, f"{type(exc).__name__}: {exc}")
        )
        raise IterationFailed(f"{name}: {type(exc).__name__}") from exc
    seconds = time.perf_counter() - started
    if response.status_code >= 400:
        outcomes.append(StepOutcome(name, seconds, False, f"HTTP {response.status_code}"))
        raise IterationFailed(f"{name}: HTTP {response.status_code}")
    outcomes.append(StepOutcome(name, seconds, True))
    return response


def _as_json(response: httpx.Response) -> dict[str, Any]:
    """Return the JSON body of *response*, or fail the step on a non-object."""
    try:
        payload = response.json()
    except ValueError as exc:
        raise IterationFailed("réponse non JSON") from exc
    if not isinstance(payload, dict):
        raise IterationFailed("réponse JSON inattendue")
    return payload


async def _await_delivery(
    client: httpx.AsyncClient,
    request_id: str,
    config: LoadConfig,
) -> tuple[float, str]:
    """Poll ``GET /v1/requests/{id}`` until the delivery is available.

    Returns the elapsed seconds and the terminal status. Le harnais n'attend pas
    une durée fixe : il attend un **état réel** du système, et le temps mesuré est
    celui de cette attente.
    """
    started = time.perf_counter()
    deadline = started + config.timeout_s
    while True:
        response = await client.get(f"/v1/requests/{request_id}")
        if response.status_code >= 400:
            raise IterationFailed(f"await_delivery: HTTP {response.status_code}")
        body = _as_json(response)
        state = body.get("pipeline_state") or {}
        status = str(state.get("status") or body.get("status") or "")
        if status in TERMINAL_STATUSES:
            return time.perf_counter() - started, status
        if time.perf_counter() >= deadline:
            raise IterationFailed(
                "await_delivery: aucun état terminal après "
                f"{config.timeout_s:g}s (dernier état : {status or 'aucun'})"
            )
        await asyncio.sleep(config.poll_interval_s)


async def run_iteration(
    client: httpx.AsyncClient,
    config: LoadConfig,
    index: int,
) -> IterationOutcome:
    """Run the whole ``upload → ingestion → delivery → download`` path once.

    Args:
        client: client HTTP déjà construit (réseau réel ou transport ASGI).
        config: paramètres de la campagne.
        index: numéro de l'itération — l'objectif diffère, donc la charge ne se
            déduplique pas en cache ; la donnée téléversée, elle, est identique.

    Returns:
        La mesure des six étapes et l'état de l'itération. Une erreur HTTP, un
        parcours incomplet ou une empreinte qui ne correspond pas donnent
        ``ok=False`` : le harnais ne déclare jamais un succès qu'il n'a pas vu.
    """
    outcomes: list[StepOutcome] = []
    request_id = artifact_id = status = None
    digest_verified = False
    try:
        # 1. La requête qui porte le téléversement.
        holder = _as_json(
            await _timed(
                outcomes,
                "submit_request",
                client.post(
                    "/v1/requests",
                    json={
                        "objective": f"Charge §41.13 — support du jeu de données #{index}",
                        "request_type": "data",
                    },
                ),
            )
        )
        holder_id = str(holder.get("request_id") or "")
        if not holder_id:
            raise IterationFailed("submit_request: aucun request_id")

        # 2. Le jeu de données est réellement téléversé (multipart + stockage objet).
        upload = _as_json(
            await _timed(
                outcomes,
                "upload_dataset",
                client.post(
                    f"/v1/requests/{holder_id}/documents",
                    files={
                        "file": (
                            BENCHMARK_DATASET_NAME,
                            benchmark_dataset(config.dataset_rows),
                            "text/csv",
                        )
                    },
                ),
            )
        )
        storage_ref = str(upload.get("storage_ref") or "")
        if not storage_ref:
            raise IterationFailed("upload_dataset: aucun storage_ref")

        # 3. Une seconde requête **nomme** l'objet : il est ingéré avant le run.
        run = _as_json(
            await _timed(
                outcomes,
                "ingest_and_run",
                client.post(
                    "/v1/requests",
                    json={
                        "objective": f"Charge §41.13 — parcours complet #{index}",
                        "request_type": "data",
                        "source_ref": storage_ref,
                        "required_output": {"format": config.required_format},
                    },
                ),
            )
        )
        request_id = str(run.get("request_id") or "")
        if not request_id:
            raise IterationFailed("ingest_and_run: aucun request_id")

        # 4. Attente de la livraison — une attente réelle sur l'état du système.
        waited, status = await _await_delivery(client, request_id, config)
        outcomes.append(StepOutcome("await_delivery", waited, True))

        # 5. L'artefact demandé (§24.2).
        listing = _as_json(
            await _timed(
                outcomes,
                "list_artifacts",
                client.get("/v1/artifacts", params={"request_id": request_id}),
            )
        )
        artifacts = listing.get("artifacts") or []
        if not artifacts:
            raise IterationFailed("list_artifacts: aucun artefact livré")
        artifact = artifacts[0]
        artifact_id = str(artifact.get("artifact_id") or "")
        expected = str(artifact.get("sha256") or "")

        # 6. Téléchargement + vérification de l'empreinte annoncée (§24.2).
        download = await _timed(
            outcomes,
            "download_artifact",
            client.get(f"/v1/artifacts/{artifact_id}/download"),
        )
        digest_verified = bool(expected) and (
            hashlib.sha256(download.content).hexdigest() == expected
        )
        if not digest_verified:
            raise IterationFailed("download_artifact: empreinte sha256 non vérifiée")
    except IterationFailed as failure:
        return IterationOutcome(
            steps=outcomes,
            ok=False,
            error=str(failure),
            request_id=request_id,
            artifact_id=artifact_id,
            status=status,
        )
    return IterationOutcome(
        steps=outcomes,
        ok=True,
        request_id=request_id,
        artifact_id=artifact_id,
        status=status,
        digest_verified=digest_verified,
    )


#: §41.13 — noms des seuils « p99 » exposés par ``GET /v1/metrics → benchmarks``,
#: et la métrique §34 du système qui les alimente. Le harnais **n'invente aucun
#: seuil** : il lit les valeurs du système chargé et compare.
THRESHOLD_METRICS: dict[str, tuple[str, str]] = {
    "vector_search_latency_p99_ms": ("vector_search_latency", "ms"),
    "postgres_query_latency_p99_ms": ("postgres_latency", "ms"),
    "amqp_message_latency_p99_ms": ("broker_latency", "ms"),
    "llm_call_latency_p99_ms": ("llm_latency", "ms"),
}

#: Clé du bloc ``benchmarks`` servant de point de comparaison au débit mesuré.
THROUGHPUT_KEY = "target_requests_per_second"

#: Seuils de **garde-fou** (bornes de configuration, pas des mesures de charge) :
#: publiés dans le résultat, jamais comptés en PASS/FAIL — ils bornent
#: l'exécution, ils ne se mesurent pas sous charge.
GUARD_THRESHOLDS: tuple[str, ...] = ("max_plan_steps", "max_parallel_tool_calls")


def percentile(samples: Sequence[float], quantile: float) -> float | None:
    """Return the *quantile* percentile of *samples* (nearest rank).

    Méthode déterministe et documentée : le harnais ne publie pas une
    interpolation dépendante d'une bibliothèque, un même échantillon donne
    toujours la même valeur.
    """
    if not samples:
        return None
    ordered = sorted(samples)
    index = max(0, math.ceil(quantile * len(ordered)) - 1)
    return ordered[min(index, len(ordered) - 1)]


def summarize(
    outcomes: Sequence[IterationOutcome],
    duration_s: float,
    *,
    config: LoadConfig,
) -> dict[str, Any]:
    """Aggregate the iterations into the measured metrics of the campaign.

    Le débit publié est celui des **parcours complets réussis** par seconde
    (§41.13 « requêtes concurrentes acceptées ») : un parcours interrompu compte
    comme une erreur, jamais comme un succès plus rapide.
    """
    total = len(outcomes)
    ok = sum(1 for outcome in outcomes if outcome.ok)
    errors = total - ok
    steps: dict[str, dict[str, Any]] = {}
    for name in SCENARIO_STEPS:
        samples = [
            step.seconds * 1000.0
            for outcome in outcomes
            for step in outcome.steps
            if step.name == name and step.ok
        ]
        failed = sum(
            1
            for outcome in outcomes
            for step in outcome.steps
            if step.name == name and not step.ok
        )
        steps[name] = {
            "measured": len(samples),
            "failed": failed,
            "p50_ms": percentile(samples, 0.50),
            "p95_ms": percentile(samples, 0.95),
            "p99_ms": percentile(samples, 0.99),
            "max_ms": max(samples) if samples else None,
        }
    return {
        "requests": total,
        "concurrency": config.concurrency,
        "ok": ok,
        "errors": errors,
        "error_rate": (errors / total) if total else None,
        "duration_s": duration_s,
        "throughput_rps": (ok / duration_s) if duration_s > 0 else None,
        "steps": steps,
        "failures": [outcome.error for outcome in outcomes if not outcome.ok][:20],
    }


def _check_status(
    observed: float | None,
    threshold: float | None,
    *,
    higher_is_better: bool = False,
) -> str:
    """Return ``pass``/``fail``/``not_measured`` for one observation.

    Le sens de la comparaison suit la métrique : un débit élevé est une réussite,
    une latence élevée est un dépassement. Comparer un débit comme une latence
    ferait passer une campagne lente pour un succès.
    """
    if observed is None or threshold is None:
        return "not_measured"
    if higher_is_better:
        return "pass" if observed >= threshold else "fail"
    return "pass" if observed <= threshold else "fail"


def evaluate_checks(
    summary: Mapping[str, Any],
    benchmarks: Mapping[str, Any],
    system_metrics: Mapping[str, Any],
    *,
    scope: str = "local",
) -> list[dict[str, Any]]:
    """Compare the measurements with the thresholds the **system** exposes.

    Args:
        summary: le résumé mesuré par le harnais (``summarize``).
        benchmarks: le bloc ``benchmarks`` de ``GET /v1/metrics`` — la source des
            seuils, telle que §41.13 la désigne (le harnais n'en invente aucun).
        system_metrics: le bloc ``metrics`` de ``GET /v1/metrics`` après la
            charge : c'est le système qui a mesuré ces p99, pas le harnais.
        scope: ``staging`` applique la comparaison ; ``local`` publie les valeurs
            observées **et** les seuils exposés sans conclure, parce que §41.13
            situe la mesure en staging — une campagne de poste de travail ne
            transforme pas une cible de staging en exigence locale.

    Returns:
        Un contrôle par seuil : valeur observée, seuil, verdict et, quand il n'y a
        rien à comparer, la raison (``not_measured``) — jamais un PASS de
        complaisance.
    """
    checks: list[dict[str, Any]] = []
    local_reason = (
        "campagne locale : le seuil exposé est une cible de staging (§41.13), "
        "comparée uniquement en portée « staging »"
    )

    # Débit : la mesure produite par le harnais lui-même.
    target = benchmarks.get(THROUGHPUT_KEY)
    observed_rps = summary.get("throughput_rps")
    broken = int(summary.get("errors") or 0) > 0
    if broken:
        status, reason = "fail", "au moins un parcours complet a échoué"
    elif scope == "staging":
        status = _check_status(observed_rps, target, higher_is_better=True)
        reason = (
            "débit observé sous le seuil exposé" if status == "fail" else None
        )
    else:
        status, reason = "not_measured", local_reason
    checks.append(
        {
            "name": "throughput_requests_per_second",
            "threshold_key": THROUGHPUT_KEY,
            "threshold": target,
            "observed": observed_rps,
            "unit": "req/s",
            "status": status,
            "reason": reason,
        }
    )

    # Latences de composant : observées par le système pendant la charge.
    for key, (metric, unit) in THRESHOLD_METRICS.items():
        entry = (system_metrics or {}).get(metric) or {}
        samples = int(entry.get("observed") or 0)
        p99 = entry.get("p99")
        threshold = benchmarks.get(key)
        if not samples:
            status, reason = "not_measured", "aucun échantillon mesuré par le système"
        elif scope == "staging":
            status = _check_status(p99, threshold)
            reason = "p99 observé au-dessus du seuil exposé" if status == "fail" else None
        else:
            status, reason = "not_measured", local_reason
        checks.append(
            {
                "name": metric,
                "threshold_key": key,
                "threshold": threshold,
                "observed": p99 if samples else None,
                "unit": unit,
                "status": status,
                "reason": reason,
            }
        )
    return checks


async def _system_metrics(client: httpx.AsyncClient) -> dict[str, Any]:
    """Read ``GET /v1/metrics``: the thresholds and the system's own samples.

    Les seuils viennent **du système chargé** (§41.13 : « exposés dans
    ``/v1/metrics`` ») et les p99 aussi : le harnais ne fabrique ni l'un ni
    l'autre. Une réponse absente ou illisible rend ``{}`` — la campagne continue
    et le dira dans ses limitations, plutôt que d'inventer un seuil.
    """
    try:
        response = await client.get("/v1/metrics")
        if response.status_code >= 400:
            return {}
        payload = response.json()
    except Exception:  # noqa: BLE001 - l'absence de métriques est dite, pas fatale
        return {}
    return payload if isinstance(payload, dict) else {}


@dataclass
class LoadResult:
    """The outcome of one campaign: the measurements and the archived record."""

    summary: dict[str, Any]
    record: dict[str, Any]

    @property
    def status(self) -> str:
        """Return ``PASS``, ``FAIL`` or ``MEASURED``."""
        return str(self.record.get("status"))


def _git_state() -> dict[str, Any]:
    """Return the commit the harness measured (``unknown`` outside a checkout)."""

    def _run(*args: str) -> str | None:
        try:
            output = subprocess.run(
                ["git", *args], capture_output=True, text=True, check=False, timeout=10
            )
        except Exception:  # noqa: BLE001 - un dépôt absent n'empêche pas de mesurer
            return None
        return output.stdout.strip() or None

    return {
        "commit": _run("rev-parse", "--short", "HEAD") or "unknown",
        "branch": _run("rev-parse", "--abbrev-ref", "HEAD") or "unknown",
        "dirty": bool(_run("status", "--porcelain")),
    }


def _overall_status(summary: Mapping[str, Any], checks: Sequence[Mapping[str, Any]]) -> str:
    """Return the campaign verdict: a broken path or a breached threshold fails."""
    if int(summary.get("errors") or 0) > 0 or any(c["status"] == "fail" for c in checks):
        return "FAIL"
    if any(c["status"] == "pass" for c in checks):
        return "PASS"
    return "MEASURED"


async def run_load(config: LoadConfig) -> LoadResult:
    """Run *config* against the real system and return the measured result.

    Le parcours complet est mené ``config.requests`` fois, ``config.concurrency``
    à la fois. Les métriques du système sont lues avant et après la charge, donc
    les p99 comparées aux seuils couvrent **cette** campagne.

    Args:
        config: paramètres de la campagne (aucun seuil n'y figure).

    Returns:
        Les mesures et l'enregistrement complet — statut ``PASS``, ``FAIL`` ou
        ``MEASURED``, plus les limitations de la campagne.
    """
    transport = httpx.ASGITransport(app=config.app) if config.app is not None else None
    before: dict[str, Any] = {}
    after: dict[str, Any] = {}
    outcomes: list[IterationOutcome] = []
    async with httpx.AsyncClient(
        base_url=config.base_url,
        transport=transport,
        timeout=config.timeout_s,
        follow_redirects=True,
    ) as client:
        before = await _system_metrics(client)
        semaphore = asyncio.Semaphore(config.concurrency)

        async def _worker(index: int) -> IterationOutcome:
            async with semaphore:
                return await run_iteration(client, config, index)

        started = time.perf_counter()
        outcomes = list(await asyncio.gather(*[_worker(i) for i in range(config.requests)]))
        duration_s = time.perf_counter() - started
        after = await _system_metrics(client)

    summary = summarize(outcomes, duration_s, config=config)
    benchmarks: dict[str, Any] = dict(after.get("benchmarks") or before.get("benchmarks") or {})
    checks = evaluate_checks(
        summary, benchmarks, after.get("metrics") or {}, scope=config.measurement_scope
    )

    limitations = list(config.notes)
    if config.measurement_scope != "staging":
        limitations.append(
            "portée « local » : les seuils exposés sont publiés à côté des mesures mais "
            "ne sont pas appliqués (§41.13 situe la mesure en staging) ; seul un parcours "
            "cassé fait échouer la campagne"
        )
    if config.app is not None:
        limitations.append(
            "chargé en process (transport ASGI) : mêmes routes, même pipeline, même base "
            "et même stockage, sans socket TCP/TLS, sans proxy ni worker uvicorn multiple"
        )
    if not benchmarks:
        limitations.append(
            "GET /v1/metrics n'a rien exposé : aucun seuil à comparer (les mesures sont "
            "publiées, aucune exigence n'est inventée)"
        )
    measured_only = [c["name"] for c in checks if c["status"] == "not_measured"]
    if measured_only:
        limitations.append(
            "seuils sans échantillon pendant cette charge (jamais comptés PASS) : "
            + ", ".join(sorted(measured_only))
        )
    limitations.append(
        "mesure locale : une campagne sur ce poste ne vaut pas une mesure de staging "
        "(§41.13 exige une mesure en environnement de staging)"
    )

    record: dict[str, Any] = {
        "harness": "tests/load/harness.py",
        "harness_version": HARNESS_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "git": _git_state(),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "cpu_count": os.cpu_count(),
        },
        "config": {
            "base_url": config.base_url,
            "requests": config.requests,
            "concurrency": config.concurrency,
            "timeout_s": config.timeout_s,
            "dataset_rows": config.dataset_rows,
            "dataset_name": BENCHMARK_DATASET_NAME,
            "required_format": config.required_format,
            "in_process": config.app is not None,
            "measurement_scope": config.measurement_scope,
        },
        "scenario": [
            f"{name}" for name in SCENARIO_STEPS
        ],
        "metrics": summary,
        "thresholds": {
            "source": "GET /v1/metrics → benchmarks (§41.13)",
            "values": benchmarks,
            "guards": {name: benchmarks.get(name) for name in GUARD_THRESHOLDS},
        },
        "checks": checks,
        "status": _overall_status(summary, checks),
        "limitations": limitations,
    }
    return LoadResult(summary=summary, record=record)


def write_result(record: Mapping[str, Any], directory: str | Path) -> Path:
    """Write one campaign record to *directory* and return its path.

    Le nom encode **l'horodatage, le commit et le verdict** : deux campagnes ne
    s'écrasent jamais, et une archive se lit sans ouvrir le fichier. Le JSON est
    trié (``sort_keys``) pour qu'un diff entre deux campagnes montre les
    changements, pas un ordre aléatoire.
    """
    folder = Path(directory)
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    commit = str((record.get("git") or {}).get("commit") or "unknown")
    status = str(record.get("status") or "UNKNOWN")
    path = folder / f"{stamp}-{commit}-{status}.json"
    path.write_text(
        json.dumps(record, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path

