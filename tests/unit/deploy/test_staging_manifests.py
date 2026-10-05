"""Deployment manifests must stay coherent with the async engine (§4.2, §41.14).

Two misconfigurations cost a real deployment and are easy to reintroduce:

* a synchronous ``postgresql://`` URL — ``migrations/env.py`` and
  ``app/storage/database/engine.py`` build an **async** engine, so a sync URL
  fails with ``No module named 'psycopg'`` (only ``asyncpg`` is installed);
* a readiness probe that never checks a dependency — ``/v1/status`` answers
  ``ready`` unconditionally, so a pod looked ready while PostgreSQL or the broker
  was down.

This guard reads the tracked manifests and fails if either regression returns.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]

#: Manifests whose database URL is consumed by the async engine / Alembic.
ASYNC_URL_FILES = (
    "docker-compose.yml",
    "docker-compose.prod.yml",
    "deploy/cloud/k8s/secrets.yaml.example",
)

_DATABASE_URL = re.compile(r"(?P<key>INIS_DATABASE_URL|DATABASE_URL):\s*(?P<url>\S+)")


class TestDatabaseUrl:
    """§4.2 — an async driver everywhere a PostgreSQL URL is declared."""

    def test_every_declared_url_uses_asyncpg(self) -> None:
        offenders: list[str] = []
        for name in ASYNC_URL_FILES:
            text = (ROOT / name).read_text(encoding="utf-8")
            for match in _DATABASE_URL.finditer(text):
                url = match.group("url").strip("\"'")
                if "postgresql" in url and "+asyncpg" not in url:
                    offenders.append(f"{name}: {match.group('key')}={url}")

        assert offenders == [], f"URL PostgreSQL sans driver async : {offenders}"

    def test_the_production_overlay_no_longer_declares_a_sync_url(self) -> None:
        text = (ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8")
        # Only the *values* matter: a comment may legitimately explain why a sync
        # URL is forbidden.
        values = [
            line
            for line in text.splitlines()
            if not line.lstrip().startswith("#")
        ]

        assert all("postgresql://" not in line for line in values), (
            "URL synchrone réintroduite dans la surcouche prod"
        )


class TestReadinessProbe:
    """§32/§34 — the readiness probe must interrogate the real contract."""

    def _container(self) -> dict:
        manifest = yaml.safe_load(
            (ROOT / "deploy/k8s/deployment.yaml").read_text(encoding="utf-8")
        )
        return manifest["spec"]["template"]["spec"]["containers"][0]

    def test_readiness_uses_the_subsystem_contract(self) -> None:
        assert self._container()["readinessProbe"]["httpGet"]["path"] == "/v1/health/ready"

    def test_liveness_stays_the_cheap_process_probe(self) -> None:
        assert self._container()["livenessProbe"]["httpGet"]["path"] == "/health"


class TestProbeReachability:
    """The probes above must be reachable **without** credentials (§19/§32).

    Measured: with ``INIS_AUTH_ENABLED=true`` these paths answered 401, so a
    Kubernetes readiness probe could never succeed. The rate limiter already
    exempts them (`EXTRA_EXEMPT_PREFIXES`); the auth middleware must too.
    """

    def test_health_and_status_are_exempt_from_auth(self) -> None:
        from app.api.middleware.auth_middleware import EXEMPT_EXACT_PATHS, EXEMPT_PREFIXES

        assert "/v1/status" in EXEMPT_EXACT_PATHS
        assert any("/v1/health".startswith(prefix) for prefix in EXEMPT_PREFIXES), (
            "/v1/health/ready doit être exempté d'authentification"
        )

    def test_the_rate_limiter_exempts_the_same_paths(self) -> None:
        from app.api.middleware.rate_limit_middleware import EXTRA_EXEMPT_PREFIXES

        assert "/v1/health" in EXTRA_EXEMPT_PREFIXES
        assert "/v1/status" in EXTRA_EXEMPT_PREFIXES


class TestProductionDependencies:
    """A dependency the documented production config needs must ship in the image."""

    def test_redis_is_a_production_dependency(self) -> None:
        import tomllib

        project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
        runtime = project["dependencies"]
        dev = project.get("optional-dependencies", {}).get("dev", [])

        assert any(dep.startswith("redis") for dep in runtime), (
            "REDIS_URL configuré (staging/production) exige le paquet `redis` dans l'image"
        )
        assert not any(dep.startswith("redis") for dep in dev), (
            "`redis` est une dépendance de production, pas seulement de test"
        )

