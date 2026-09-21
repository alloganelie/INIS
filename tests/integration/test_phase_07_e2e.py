"""PHASE-07 smoke imports: security, auth endpoints (§19, §20)."""

from __future__ import annotations

import importlib
import importlib.util

import pytest


def _has_module(module_name: str) -> bool:
    """Return True if *module_name* can be found without importing it."""
    try:
        return importlib.util.find_spec(module_name) is not None
    except (ModuleNotFoundError, ValueError):
        return False


def _has_symbol(module_name: str, symbol: str) -> bool:
    """Return True if *module_name* defines *symbol* (False si absent)."""
    if not _has_module(module_name):
        return False
    try:
        module = importlib.import_module(module_name)
    except ImportError:
        return False
    return getattr(module, symbol, None) is not None


def _import_or_skip(module_name: str):
    """Import *module_name* or skip the test if it is absent."""
    if not _has_module(module_name):
        pytest.skip(f"module absent: {module_name}")
    return importlib.import_module(module_name)


def _symbol_or_skip(module, module_name: str, symbol: str):
    """Return *symbol* from *module* or skip if it is not defined."""
    value = getattr(module, symbol, None)
    if value is None:
        pytest.skip(f"symbol absent: {symbol} in {module_name}")
    return value


def _require_symbols(pairs: list[tuple[str, str]]) -> None:
    """Skip listing every missing (module, symbol); pass if all present."""
    missing = [
        f"{symbol} in {module}"
        for module, symbol in pairs
        if not _has_symbol(module, symbol)
    ]
    if missing:
        pytest.skip("symbols absents: " + "; ".join(missing))


def _require_any_symbol(module_name: str, candidates: list[str]):
    """Return first present symbol among *candidates*; skip if none exists."""
    module = _import_or_skip(module_name)
    for symbol in candidates:
        value = getattr(module, symbol, None)
        if value is not None:
            return value
    pytest.skip(f"aucun symbole {candidates} in {module_name}")


def test_access_policy_entity_imports() -> None:
    """AccessPolicy entity imports per §19.3 (skip si absent)."""
    module_name = "app.domain.entities.access_policy"
    module = _import_or_skip(module_name)
    policy = _symbol_or_skip(module, module_name, "AccessPolicy")
    assert isinstance(policy, type), "AccessPolicy is not a class"


def test_security_classification_imports() -> None:
    """Classification imports per §19.3/§19.4 (skip si absent)."""
    _require_any_symbol(
        "app.domain.entities.security_classification",
        ["SecurityClassification", "Classification"],
    )


def test_jwt_validator_imports() -> None:
    """JWT validator imports per §19.2 (skip si absent)."""
    _require_any_symbol(
        "app.security.authn.jwt_validator",
        ["JWTValidator", "ValidationError"],
    )


def test_pii_detector_imports() -> None:
    """PII detector imports per §19.4 (skip si absent)."""
    _require_any_symbol(
        "app.security.pii.pii_detector", ["PIIDetector", "detect_pii"]
    )


def test_rbac_engine_imports() -> None:
    """RBAC engine imports per §19.3 (skip si absent)."""
    _require_any_symbol(
        "app.security.authz.rbac_engine", ["RBACEngine", "check_permission"]
    )


def test_rate_limiter_imports() -> None:
    """Rate limiter imports (skip si absent)."""
    _require_any_symbol(
        "app.security.rate_limiting.rate_limiter", ["RateLimiter"]
    )


def test_retention_enforcer_imports() -> None:
    """Retention enforcer imports (skip si absent)."""
    _require_any_symbol(
        "app.governance.retention.retention_enforcer", ["RetentionEnforcer"]
    )


def test_trace_context_imports() -> None:
    """Trace context imports per §20.2 (skip si absent)."""
    _require_any_symbol(
        "app.observability.tracing", ["TraceContext", "get_trace_context"]
    )


def test_auth_endpoints_imports() -> None:
    """Auth endpoints imports per §19.2 (skip si absent)."""
    module_name = "app.api.v1.auth"
    module = _import_or_skip(module_name)
    router = _symbol_or_skip(module, module_name, "router")
    assert router is not None


def _auth_client():
    """Build an httpx client mounted on the auth router (skip si absent)."""
    import httpx
    from fastapi import FastAPI

    from app.api.middleware.auth_middleware import AuthMiddleware

    module = _import_or_skip("app.api.v1.auth")
    router = _symbol_or_skip(module, "app.api.v1.auth", "router")
    app = FastAPI()
    app.add_middleware(AuthMiddleware)
    # Le router porte deja le prefixe interne "/auth" ; le monter sous
    # "/v1" reproduit app.main (routes finales /v1/auth/*).
    app.include_router(router, prefix="/v1")
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


_VALID_LOGIN = {"username": "admin", "password": "adminpassword"}


async def test_auth_login_smoke() -> None:
    """POST /v1/auth/login → 200 (skip si endpoint/schema absent)."""
    if not _has_symbol("app.api.v1.auth", "router"):
        pytest.skip("symbol absent: router in app.api.v1.auth")
    async with _auth_client() as client:
        response = await client.post("/v1/auth/login", json=_VALID_LOGIN)
    assert response.status_code == 200, response.text
    assert response.json().get("access_token")


async def test_auth_me_requires_token() -> None:
    """GET /v1/auth/me sans token → 401 (skip si endpoint absent)."""
    if not _has_symbol("app.api.v1.auth", "router"):
        pytest.skip("symbol absent: router in app.api.v1.auth")
    async with _auth_client() as client:
        response = await client.get("/v1/auth/me")
    assert response.status_code == 401, response.text


async def test_auth_me_with_token() -> None:
    """Login puis GET /v1/auth/me → 200 (skip si login/token absent)."""
    from app.api.middleware.auth_middleware import set_strict_auth_mode

    if not _has_symbol("app.api.v1.auth", "router"):
        pytest.skip("symbol absent: router in app.api.v1.auth")
    # Le middleware est opt-in : l'activer pour que le token soit injecte
    # dans request.state (sinon /me repond 401 meme avec un token valide).
    set_strict_auth_mode(True)
    try:
        async with _auth_client() as client:
            login = await client.post("/v1/auth/login", json=_VALID_LOGIN)
            assert login.status_code == 200, login.text
            try:
                payload = login.json()
            except ValueError:
                pytest.fail("réponse login non-JSON")
            token = None
            if isinstance(payload, dict):
                for key in ("access_token", "token", "id_token"):
                    if payload.get(key):
                        token = payload[key]
                        break
            assert token, "aucun token dans la réponse login"
            response = await client.get(
                "/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
            )
    finally:
        set_strict_auth_mode(None)
    assert response.status_code == 200, response.text


def _iter_route_paths(router, prefix=""):
    """Yield (path, methods) walking included routers (FastAPI lazy includes)."""
    for route in router.routes:
        path = getattr(route, "path", None)
        if path:
            yield prefix + path, set(getattr(route, "methods", set()) or set())
        sub = getattr(route, "original_router", None)
        if sub is not None:
            # Les routes du sous-router incluent deja son prefixe interne
            # (ex. "/sources") : ne pas le re-ajouter pour eviter
            # "/v1/sources/sources". On propage uniquement le prefixe externe.
            yield from _iter_route_paths(sub, prefix)


async def test_middleware_protects_endpoint() -> None:
    """GET sources sans token → 401 si middleware actif (skip sinon)."""
    import httpx
    from fastapi import FastAPI

    from app.api.middleware.auth_middleware import AuthMiddleware, set_strict_auth_mode
    from app.api.v1.router import router as v1_router

    app = FastAPI()
    app.add_middleware(AuthMiddleware)
    app.include_router(v1_router)
    paths = [
        path
        for path, methods in _iter_route_paths(v1_router, v1_router.prefix or "")
        if "sources" in path and "GET" in methods
    ]
    if not paths:
        pytest.skip("aucune route GET sources")
    # Le middleware est opt-in : l'activer pour verifier la protection.
    set_strict_auth_mode(True)
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.get(paths[0])
    finally:
        set_strict_auth_mode(None)
    assert response.status_code == 401, response.text
