"""§41.8 — la politique retry/disjoncteur couvre-t-elle les **nouveaux** chemins ?

L'ADR ``006_circuit_breaker_per_connector.md`` et le module
``app/connectors/resilience/circuit_breaker.py`` existaient, mais **aucun chemin
de ``app/`` ne les appelait** : le disjoncteur était un composant testé en
isolation, jamais consulté par du code réel. Ce fichier vérifie :

* le contrat de ``guard`` / ``guard_sync`` : succès, échecs transitoires,
  épuisement des tentatives, circuit ouvert **sans appel** ;
* les chemins réellement concernés — l'acquisition web du pipeline (§41.8) et
  l'upload d'artefact vers le stockage objet — et pas seulement le mécanisme ;
* deux refus : un échec n'est jamais transformé en faux succès.

Ce qui n'est **pas** protégé par un disjoncteur, et pourquoi, est écrit dans
:class:`TestWhatIsNotBehindABreaker`.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.connectors.resilience.circuit_breaker import (
    CircuitBreakerConfig,
    CircuitBreakerRegistry,
    CircuitOpenError,
    guard,
    guard_sync,
)


def _registry(threshold: int = 2, recovery: float = 30.0) -> CircuitBreakerRegistry:
    """A registry whose thresholds are small enough to open in one test."""
    return CircuitBreakerRegistry(
        default_config=CircuitBreakerConfig(
            failure_threshold=threshold,
            recovery_timeout_seconds=recovery,
            half_open_max_calls=1,
        )
    )


async def _never_sleep(_: float) -> None:
    """Replace ``asyncio.sleep`` so a retry costs no wall-clock time."""
    return


def _transient(failures: int, value: str = "ok") -> tuple[Any, list[int]]:
    """Return a callable failing *failures* times, and the call counter."""
    calls: list[int] = []

    async def call() -> str:
        calls.append(len(calls) + 1)
        if len(calls) <= failures:
            raise TimeoutError("dépendance momentanément indisponible")
        return value

    return call, calls


class TestTheGuardContract:
    """Succès, échecs transitoires, épuisement, circuit ouvert."""

    async def test_a_successful_call_is_recorded_as_success(self) -> None:
        registry = _registry()
        call, calls = _transient(0)

        result = await guard("provider:test", call, breaker_registry=registry)

        assert result == "ok"
        assert calls == [1], "un succès ne se rejoue pas"
        assert registry.get("provider:test").failure_count == 0

    async def test_a_transient_failure_is_retried(self) -> None:
        registry = _registry()
        call, calls = _transient(2)

        result = await guard(
            "provider:test",
            call,
            breaker_registry=registry,
            max_attempts=3,
            sleep=_never_sleep,
        )

        assert result == "ok"
        assert calls == [1, 2, 3], "les deux échecs transitoires ont été retentés"

    async def test_exhausted_retries_raise_the_real_error(self) -> None:
        registry = _registry()
        call, calls = _transient(99)

        with pytest.raises(TimeoutError, match="indisponible"):
            await guard(
                "provider:test",
                call,
                breaker_registry=registry,
                max_attempts=3,
                sleep=_never_sleep,
            )

        assert calls == [1, 2, 3]
        assert registry.get("provider:test").failure_count == 1, (
            "l'appel logique échoue une fois ; les tentatives ne sont pas des "
            "pannes distinctes, sinon un simple flake ouvrirait le circuit"
        )

    async def test_an_open_circuit_refuses_without_calling(self) -> None:
        registry = _registry(threshold=1)
        registry.get("provider:test").record_failure()
        call, calls = _transient(0)

        with pytest.raises(CircuitOpenError):
            await guard("provider:test", call, breaker_registry=registry)

        assert calls == [], "un circuit ouvert ne doit pas laisser partir l'appel"

    async def test_a_retry_never_produces_a_false_success(self) -> None:
        """Le disjoncteur ouvert ne renvoie pas ``[]`` : il refuse."""
        registry = _registry(threshold=1)
        broken, _ = _transient(99)

        with pytest.raises(Exception):  # noqa: B017 - le type exact n'importe pas ici
            await guard("provider:test", broken, breaker_registry=registry, max_attempts=1)
        with pytest.raises(CircuitOpenError):
            await guard("provider:test", broken, breaker_registry=registry, max_attempts=1)

    def test_the_sync_twin_refuses_without_calling(self) -> None:
        registry = _registry(threshold=1)
        registry.get("connector:s3").record_failure()
        calls: list[int] = []

        with pytest.raises(CircuitOpenError):
            guard_sync(
                "connector:s3",
                lambda: calls.append(1) or "uploaded",
                breaker_registry=registry,
            )

        assert calls == []

    def test_the_sync_twin_records_a_success(self) -> None:
        registry = _registry()
        assert guard_sync("connector:s3", lambda: "uploaded", breaker_registry=registry) == (
            "uploaded"
        )
        assert registry.get("connector:s3").failure_count == 0


class TestTheRealPathsUseIt:
    """Les chemins concernés, pas le mécanisme : le pipeline et le stockage objet."""

    async def test_the_pipeline_web_search_is_retried_on_transient_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """§41.8 — l'acquisition web subit la panne passagère, pas l'utilisateur."""
        from app.api.v1.requests.pipeline_runner import PipelineRunner
        from app.connectors.resilience import circuit_breaker as breaker_module

        registry = _registry()
        monkeypatch.setattr(breaker_module, "registry", registry)

        class _FlakyProvider:
            """Un fournisseur qui échoue une fois, puis répond."""

            _default_provider_id = "flaky"

            def __init__(self) -> None:
                self.calls = 0

            async def search(self, query: str, limit: int) -> list[dict[str, Any]]:
                self.calls += 1
                if self.calls == 1:
                    raise TimeoutError("timeout amont")
                return [{"title": "Paris", "url": "https://exemple.invalid/p"}]

        provider = _FlakyProvider()
        results = await PipelineRunner()._search_with_cache(provider, "Paris", 5)

        assert provider.calls == 2, "la première tentative échoue, la seconde aboutit"
        assert results and results[0]["title"] == "Paris"

    async def test_the_pipeline_reports_a_dead_provider_instead_of_a_false_result(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Un fournisseur mort ouvre le circuit ; l'échec reste visible."""
        from app.api.v1.requests.pipeline_runner import PipelineRunner
        from app.connectors.resilience import circuit_breaker as breaker_module

        registry = _registry(threshold=1)
        monkeypatch.setattr(breaker_module, "registry", registry)

        class _DeadProvider:
            _default_provider_id = "dead"

            def __init__(self) -> None:
                self.calls = 0

            async def search(self, query: str, limit: int) -> list[dict[str, Any]]:
                self.calls += 1
                raise ConnectionError("fournisseur injoignable")

        provider = _DeadProvider()

        with pytest.raises(ConnectionError):
            await PipelineRunner()._search_with_cache(provider, "Paris", 5)
        with pytest.raises(CircuitOpenError):
            await PipelineRunner()._search_with_cache(provider, "Paris", 5)

        assert provider.calls == 3, "seul l'épuisement est tenté, puis le circuit s'ouvre"


class TestWhatIsNotBehindABreaker:
    """Ce qui reste **volontairement** hors disjoncteur, et la raison."""

    def test_writes_are_not_retried_and_local_paths_have_no_breaker(self) -> None:
        """§41.8 vise les dépendances **distantes** rejouables, pas toute écriture.

        PostgreSQL est dans le périmètre transactionnel du processus : un échec
        d'écriture doit remonter tel quel, car rejouer une écriture risque un
        doublon. Un fichier local n'est pas une dépendance réseau. Les entrées de
        cache (§41.5) et les points de reprise (§41.1) suivent la même règle :
        leur écriture est *best effort* et signalée, jamais rejouée à l'aveugle.
        """
        from pathlib import Path

        storage_root = Path("app/storage")
        for source in ("cache/postgres_backend.py", "repositories/checkpoint_repository.py"):
            text = (storage_root / source).read_text(encoding="utf-8")
            assert "guard" not in text, (
                f"{source} ne doit pas passer par un disjoncteur : une écriture de "
                "stockage n'est pas un appel distant rejouable"
            )

        packager = Path("app/artifacts/packager/artifact_packager.py").read_text(
            encoding="utf-8"
        )
        assert "guard_sync(" in packager and '"connector:s3"' in packager, (
            "l'upload vers le stockage objet doit passer par le disjoncteur §41.8"
        )
        assert "WEB_SEARCH_ATTEMPTS" not in packager, (
            "et il ne doit pas être retenté : c'est une écriture"
        )
