"""§19 — le rate limiting est **persistant**, et c'est prouvé sur le chemin HTTP réel.

Le plan réclamait deux choses que la suite ne démontrait pas :

* le store partagé existe (`RedisRateLimitStore`, script Lua atomique) mais **aucun
  test** ne vérifiait qu'un dépassement observé par une instance soit observé par
  une **autre** — c'est-à-dire que la limite ne dépend pas de l'état mémoire du
  processus ;
* le middleware est monté (`app/main.py`) mais la preuve HTTP ne dépassait jamais
  la limite avec un backend réel.

Ce que ce fichier établit, contre un **vrai Valkey** (`redis_url`, image
`valkey/valkey:8-alpine` — dette n°1 : les tests reproduisent le serveur de
production, le client reste `redis.asyncio` et parle le protocole Redis) :

* la limite est **consommée dans le backend partagé** : deux limiteurs distincts
  (deux « processus ») voient le même bucket ;
* le chemin HTTP réel rend ``429`` + ``Retry-After`` au dépassement, et
  ``X-RateLimit-*`` sur les succès mesurés ;
* le budget vient de la **configuration** (``RATE_LIMIT_RPM``) ;
* les scopes sont **isolés** (un acteur épuisé ne consomme pas le budget d'un autre) ;
* backend **indisponible** : l'erreur est **bruyante** (aucun « laisser passer »
  silencieux), tandis qu'une configuration invalide **au démarrage** retombe sur
  des buckets process-local — jamais sur une absence de mesure ;
* **contre-épreuve** : avec des stores en mémoire, le même scénario *ne partage
  rien*. Si ce test-là échouait, les preuves de partage ne prouveraient rien.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from starlette.requests import Request

from app.api.middleware.rate_limit_middleware import (
    ANONYMOUS_KEY,
    RateLimitMiddleware,
    rate_limit_enabled,
    resolve_requests_per_minute,
)
from app.core.errors import InfrastructureError
from app.main import app
from app.security.rate_limiting.rate_limit_store import RateLimitStore
from app.security.rate_limiting.rate_limiter import RateLimiter
from app.security.rate_limiting.redis_rate_limit_store import RedisRateLimitStore

#: Endpoint volontairement mort : « backend indisponible » sans toucher au
#: conteneur partagé (l'arrêter casserait les autres tests de la session).
DEAD_ENDPOINT = "redis://127.0.0.1:1/0"

#: Budgets utilisés par les tests HTTP (petits : le dépassement est rapide).
TIGHT_RPM = 2


@pytest.fixture(autouse=True)
def _metering_on(monkeypatch: pytest.MonkeyPatch) -> None:
    """Activer la mesure, sans dépendre de l'authentification (§19)."""
    monkeypatch.setenv("INIS_RATE_LIMIT_ENABLED", "true")
    monkeypatch.delenv("RATE_LIMIT_RPM", raising=False)


def _app(limiter: RateLimiter | None, requests_per_minute: int) -> FastAPI:
    """Build a real app carrying the real middleware on *limiter*.

    Même classe, même ``dispatch``, mêmes réponses que l'application : c'est le
    chemin HTTP, pas un test unitaire du store. ``limiter=None`` laisse le
    middleware résoudre le sien depuis l'environnement (chemin de production).
    """
    app = FastAPI()
    app.add_middleware(
        RateLimitMiddleware,
        requests_per_minute=requests_per_minute,
        limiter=limiter,
    )

    @app.middleware("http")
    async def actor(request: Any, call_next: Any) -> Any:
        request.state.actor_id = request.headers.get("x-actor", "anonymous_actor")
        return await call_next(request)

    @app.get("/v1/ping")
    def ping() -> dict[str, str]:
        return {"pong": "ok"}

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


def _transport(app: FastAPI) -> httpx.ASGITransport:
    """Return an in-process ASGI transport (real HTTP semantics, no socket)."""
    return httpx.ASGITransport(app=app)


async def _drain(limiter: RateLimiter, key: str, capacity: int) -> list[bool]:
    """Consume *capacity* + 1 tokens and return the allowed flags."""
    return [(await limiter.is_allowed(key, capacity, capacity / 60.0))[0] for _ in range(capacity + 1)]


class TestHttpPath:
    """Le chemin HTTP réel : succès mesurés, puis refus au dépassement."""

    async def test_the_real_app_meters_a_mounted_endpoint(self) -> None:
        """L'application réellement montée applique la limite (§19)."""
        async with httpx.AsyncClient(
            transport=_transport(app), base_url="http://test"
        ) as client:
            metered = await client.get("/v1/agents")
            exempt = await client.get("/health")

        assert metered.status_code == 200
        assert metered.headers["X-RateLimit-Limit"] == str(resolve_requests_per_minute())
        assert "X-RateLimit-Limit" not in exempt.headers, "les sondes ne sont jamais mesurées"

    async def test_the_middleware_returns_429_from_the_shared_budget(
        self, redis_url: str
    ) -> None:
        """Au dépassement : 429 + ``Retry-After`` + corps stable, budget = config."""
        limiter = RateLimiter.from_env(redis_url)
        try:
            await limiter.store.clear_all()
            async with httpx.AsyncClient(
                transport=_transport(_app(limiter, TIGHT_RPM)), base_url="http://test"
            ) as client:
                headers = {"x-actor": "spender"}
                first = await client.get("/v1/ping", headers=headers)
                second = await client.get("/v1/ping", headers=headers)
                limited = await client.get("/v1/ping", headers=headers)

            assert (first.status_code, second.status_code) == (200, 200)
            assert first.headers["X-RateLimit-Limit"] == str(TIGHT_RPM)
            assert first.headers["X-RateLimit-Remaining"] == "1"
            assert limited.status_code == 429
            body = limited.json()
            assert body["detail"] == "Rate limit exceeded"
            assert body["limit"] == TIGHT_RPM
            assert body["window"] == "minute"
            assert int(limited.headers["Retry-After"]) >= 1
            assert body["retry_after"] == int(limited.headers["Retry-After"])
        finally:
            await limiter.store.clear_all()
            await limiter.aclose()

    async def test_a_second_application_sees_the_budget_already_spent(
        self, redis_url: str
    ) -> None:
        """Deux applications, un seul budget : c'est cela, la persistance."""
        first = RateLimiter.from_env(redis_url)
        second = RateLimiter.from_env(redis_url)
        try:
            await first.store.clear_all()

            async with httpx.AsyncClient(
                transport=_transport(_app(first, TIGHT_RPM)), base_url="http://a"
            ) as client_a:
                opened = await client_a.get("/v1/ping", headers={"x-actor": "shared"})

            async with httpx.AsyncClient(
                transport=_transport(_app(second, TIGHT_RPM)), base_url="http://b"
            ) as client_b:
                spent = await client_b.get("/v1/ping", headers={"x-actor": "shared"})
                refused = await client_b.get("/v1/ping", headers={"x-actor": "shared"})

            assert opened.status_code == 200
            assert spent.status_code == 200, "le 2e token était encore disponible"
            assert spent.headers["X-RateLimit-Remaining"] == "0"
            assert refused.status_code == 429, "B doit voir le budget déjà dépensé par A"
        finally:
            await first.store.clear_all()
            await first.aclose()
            await second.aclose()


class TestSharedBudget:
    """La limite vit dans le backend partagé, pas dans la mémoire du processus."""


    async def test_a_second_instance_inherits_the_spent_budget(self, redis_url: str) -> None:
        """Instance A épuise le budget ; l'instance B le constate."""
        first = RateLimiter.from_env(redis_url)
        second = RateLimiter.from_env(redis_url)
        assert isinstance(first.store, RedisRateLimitStore)
        assert not isinstance(first.store, RateLimitStore), "le backend doit être partagé"
        assert first.store is not second.store, "deux instances, deux clients"
        try:
            await first.store.clear_all()
            key = "scope:instance-a"

            assert await _drain(first, key, TIGHT_RPM) == [True, True, False]

            allowed, _ = await second.is_allowed(key, TIGHT_RPM, TIGHT_RPM / 60.0)
            assert allowed is False, "le budget dépensé par A doit être vu par B"
        finally:
            await first.store.clear_all()
            await first.aclose()
            await second.aclose()

    async def test_the_bucket_is_written_into_valkey(self, redis_url: str) -> None:
        """Preuve directe : la clé existe dans le serveur, et elle expire."""
        limiter = RateLimiter.from_env(redis_url)
        store = limiter.store
        assert isinstance(store, RedisRateLimitStore)
        try:
            await store.clear_all()
            await limiter.is_allowed("scope:valkey", TIGHT_RPM, TIGHT_RPM / 60.0)

            keys = [key async for key in store.client.scan_iter(match=f"{store.prefix}*")]

            assert keys, "le bucket doit être écrit dans le backend partagé"
            written = keys[0].decode("utf-8") if isinstance(keys[0], bytes) else str(keys[0])
            assert store.prefix in written, f"le bucket doit porter le préfixe : {written}"
            assert await store.client.ttl(keys[0]) > 0
        finally:
            await store.clear_all()
            await limiter.aclose()

    async def test_without_a_shared_store_nothing_is_shared(self, redis_url: str) -> None:
        """Contre-épreuve : en mémoire, deux instances ne partagent rien.

        Si ce test échouait — c'est-à-dire si un compteur local suffisait —, les
        preuves de partage ci-dessus ne démontreraient rien.
        """
        first = RateLimiter(RateLimitStore())
        second = RateLimiter(RateLimitStore())
        key = "scope:local"

        assert await _drain(first, key, TIGHT_RPM) == [True, True, False]

        allowed, _ = await second.is_allowed(key, TIGHT_RPM, TIGHT_RPM / 60.0)
        assert allowed is True, "un compteur local repart plein : rien n'est partagé"

    async def test_two_scopes_have_independent_budgets(self, redis_url: str) -> None:
        """L'isolation des scopes : épuiser l'un ne consomme pas l'autre."""
        limiter = RateLimiter.from_env(redis_url)
        try:
            await limiter.store.clear_all()

            assert await _drain(limiter, "actor-a", 1) == [True, False]

            allowed, _ = await limiter.is_allowed("actor-b", 1, 1 / 60.0)
            assert allowed is True
        finally:
            await limiter.store.clear_all()
            await limiter.aclose()

class TestConfiguration:
    """§6 — le comportement suit la configuration, il n'est pas figé dans le code."""

    async def test_the_budget_follows_the_configuration(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Changer ``RATE_LIMIT_RPM`` change réellement les requêtes admises."""
        monkeypatch.setenv("RATE_LIMIT_RPM", "3")
        wide = resolve_requests_per_minute()
        monkeypatch.setenv("RATE_LIMIT_RPM", "1")
        narrow = resolve_requests_per_minute()
        assert (wide, narrow) == (3, 1), "la configuration est lue, pas supposée"

        async with httpx.AsyncClient(
            transport=_transport(_app(RateLimiter(RateLimitStore()), wide)),
            base_url="http://wide",
        ) as client:
            statuses = [
                (await client.get("/v1/ping", headers={"x-actor": "cfg"})).status_code
                for _ in range(4)
            ]
        assert statuses == [200, 200, 200, 429]

        async with httpx.AsyncClient(
            transport=_transport(_app(RateLimiter(RateLimitStore()), narrow)),
            base_url="http://narrow",
        ) as client:
            statuses = [
                (await client.get("/v1/ping", headers={"x-actor": "cfg"})).status_code
                for _ in range(2)
            ]
        assert statuses == [200, 429]

    async def test_an_explicit_setting_wins(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Désactivation explicite : plus aucune mesure, quel que soit le budget."""
        monkeypatch.setenv("INIS_RATE_LIMIT_ENABLED", "false")
        assert rate_limit_enabled() is False

        async with httpx.AsyncClient(
            transport=_transport(_app(RateLimiter(RateLimitStore()), 1)),
            base_url="http://off",
        ) as client:
            statuses = [(await client.get("/v1/ping")).status_code for _ in range(3)]
        assert statuses == [200, 200, 200]


class TestDegradedBackends:
    """§8 — ce que fait INIS quand le backend n'est pas là."""

    async def test_an_unreachable_backend_refuses_loudly(self) -> None:
        """Backend indisponible : l'erreur remonte, jamais un laisser-passer."""
        limiter = RateLimiter.from_env(DEAD_ENDPOINT)
        try:
            async with httpx.AsyncClient(
                transport=_transport(_app(limiter, TIGHT_RPM)), base_url="http://dead"
            ) as client:
                with pytest.raises(InfrastructureError, match="rate limit"):
                    await client.get("/v1/ping", headers={"x-actor": "dead"})
        finally:
            await limiter.aclose()

    async def test_a_misconfigured_endpoint_never_leaves_the_api_unmetered(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Endpoint invalide au démarrage : buckets process-local, API debout **et mesurée**."""
        monkeypatch.setenv("REDIS_URL", "pas-une-url")
        async with httpx.AsyncClient(
            transport=_transport(_app(None, 1)), base_url="http://fallback"
        ) as client:
            first = await client.get("/v1/ping", headers={"x-actor": "fallback"})
            second = await client.get("/v1/ping", headers={"x-actor": "fallback"})

        assert first.status_code == 200
        assert first.headers["X-RateLimit-Limit"] == "1"
        assert second.status_code == 429, "le repli mesure encore"


class TestRegressions:
    """Ce qui ne doit pas changer."""

    async def test_the_exempt_paths_keep_working_over_the_limit(
        self, redis_url: str
    ) -> None:
        """Sondes et docs restent disponibles alors que le budget est épuisé."""
        limiter = RateLimiter.from_env(redis_url)
        try:
            await limiter.store.clear_all()
            async with httpx.AsyncClient(
                transport=_transport(_app(limiter, 1)), base_url="http://exempt"
            ) as client:
                spent = await client.get("/v1/ping", headers={"x-actor": "reg"})
                refused = await client.get("/v1/ping", headers={"x-actor": "reg"})
                probes = [(await client.get("/health")).status_code for _ in range(3)]

            assert (spent.status_code, refused.status_code) == (200, 429)
            assert probes == [200, 200, 200]
        finally:
            await limiter.store.clear_all()
            await limiter.aclose()


class TestKeyHygiene:
    """§14 — la clé de bucket ne contient aucun secret et reste déterministe."""

    def test_an_api_key_never_lands_in_the_bucket_key(self) -> None:
        """Les 32 premiers caractères d'une clé d'API étaient écrits dans le store."""
        secret = "sk-live-5UP3R-53CR3T-DU-TEST"
        middleware = RateLimitMiddleware(_app(None, 60), requests_per_minute=60)

        key = middleware.bucket_key(_request({"x-api-key": secret}))

        assert secret not in key
        assert "5UP3R" not in key, "aucun fragment de la clé d'API n'est stocké"
        assert key.startswith("apikey:")
        assert middleware.bucket_key(_request({"x-api-key": secret})) == key
        assert middleware.bucket_key(_request({"x-api-key": "autre-cle"})) != key

    def test_the_actor_wins_and_the_host_is_the_last_resort(self) -> None:
        """Le scope est l'acteur authentifié ; l'IP n'est qu'un dernier recours."""
        middleware = RateLimitMiddleware(_app(None, 60), requests_per_minute=60)

        keyed = middleware.bucket_key(_request({"x-api-key": "cle"}, actor="actor-1"))
        assert keyed == "actor-1"
        assert middleware.bucket_key(_request(host="203.0.113.7")) == "ip:203.0.113.7"
        assert middleware.bucket_key(_request(host="")) == ANONYMOUS_KEY


def _request(
    headers: dict[str, str] | None = None,
    *,
    host: str = "1.2.3.4",
    actor: str | None = None,
) -> Request:
    """Build a minimal ASGI request for the bucket-key contract (§19)."""
    scope: dict[str, Any] = {
        "type": "http",
        "method": "GET",
        "path": "/v1/ping",
        "query_string": b"",
        "headers": [
            (name.lower().encode("latin-1"), value.encode("latin-1"))
            for name, value in (headers or {}).items()
        ],
        "client": (host, 1234),
        "state": {},
    }
    request = Request(scope)
    if actor is not None:
        request.state.actor_id = actor
    return request

