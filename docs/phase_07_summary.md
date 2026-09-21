# PHASE-07 — Résumé factuel (lot 1 : E2E Security)

Phase active (`agent_workspace/CURRENT_PHASE.md`) : **PHASE-07 Security — 🚀 À LANCER**.
Objectif : authentification JWT (§19.2), autorisation RBAC+ABAC (§19.3), PII (§19.4),
audit renforcé (§20).
Référence spec : INIS_SPEC.md §19 (pipeline auth → authz → policy → accès → redaction),
§20 (audit event, trace) ; tests §33.

Point d'intégration Cursor : branche `agent/cursor/integration`, lot basé sur `5c0cca3`
(`docs(phase): close PHASE-06, open PHASE-07`). État de départ : 299 passed, 0 skipped.

## Zones couvertes par ce lot

| Test | Zone observée | État constaté |
|---|---|---|
| `test_access_policy_entity_imports` | `app/domain/entities/access_policy.py` | **fichier vide (0 octet) → skip** |
| `test_security_classification_imports` | `app/domain/entities/classification.py` | **fichier vide ; aucun `SecurityClassification` dans `app/` → skip** |
| `test_jwt_validator_imports` | `app/security/authn/jwt_validator.py` | **fichier vide → skip** (tout `app/security/` est stub) |
| `test_pii_detector_imports` | `app/security/pii/pii_detector.py` | **fichier vide → skip** |
| `test_rbac_engine_imports` | `app/security/authz/rbac_engine.py` | **fichier vide → skip** |
| `test_rate_limiter_imports` | `app/security/rate_limiting/rate_limiter.py` | **fichier vide → skip** |
| `test_retention_enforcer_imports` | `app/governance/retention/` | **aucune occurrence `retention` dans `app/` → skip** |
| `test_trace_context_imports` | `app/observability/tracing.py` | **fichier vide → skip** |
| `test_auth_endpoints_imports` | `app/api/v1/auth` | **répertoire inexistant → skip** |
| `test_auth_login_smoke` | POST `/v1/auth/login` → 200 (httpx ASGI) | **skip (pas de router auth)** |
| `test_auth_me_requires_token` | GET `/v1/auth/me` sans token → 401 | **skip (pas de router auth)** |
| `test_auth_me_with_token` | login puis GET `/v1/auth/me` → 200 | **skip (pas de router auth)** |
| `test_middleware_protects_endpoint` | GET sources sans token → 401 si middleware actif | **skip (status=404, voir observation)** |

## Tests ajoutés par ce lot

`tests/integration/test_phase_07_e2e.py` : 13 tests, pattern repris
(`_has_module`, `_has_symbol`, `_import_or_skip`, `_symbol_or_skip`, `_require_symbols`)
+ helper `_require_any_symbol` (accepte plusieurs noms candidats sans inventer de contrat)
et `_iter_route_paths` (découverte récursive des routes, FastAPI 0.141.1 à includes paresseux
`_IncludedRouter`). HTTP via `httpx.ASGITransport` (aucun serveur requis). Chaque test
HTTP n'assert que le status specifié et skippe sinon. Résultat attendu : 13 skippés
avec motif explicite.

## Observation — routage imbriqué FastAPI 0.141 (hors zone, à investiguer)

Vérifié contre la vraie app (`app.main:app`) : `GET /v1/status` → 200 et `/health` → 200,
mais `GET /v1/sources/sources` → **404**. Les `include_router` imbriqués restent à l'état
`_IncludedRouter` non résolu pour le dispatch des routes imbriquées. Chemins réels
découverts par marche récursive : `GET/POST /v1/sources/sources`,
`GET /v1/sources/sources/{id}` (préfixe doublé `/sources/sources`, pré-existant).
À investiguer par Antigravity (pinning FastAPI ou aplatissement des routers) ;
aucune modification faite ici (zone `app/` interdite).

Autres warnings pré-existants observés (non touchés) : `Duplicate Operation ID`
(`quality/router.py` vs conflits) lors de `app.openapi()`.

## Dettes restantes (propriétaires pressentis)

1. Entité `AccessPolicy` §19.3 (`policy_id`, subject, resource, action, effect) — Codex.
2. Classification §19.3/§19.4 (`public|internal|confidential|restricted`, PII) — Codex.
3. `app/security/authn/` : JWT (§19.2), mTLS, API keys — vide — Devin.
4. `app/security/authz/` : RBAC+ABAC §19.3 — vide — Devin.
5. `app/security/pii/` : détection, redaction, sensibilité §19.4 — vide — Devin.
6. Rate limiting, vault/credentials — vides — Devin.
7. Rétention : aucun module dans `app/` — à cadrer (Devin/Codex).
8. Trace distribuée §20.2 (`tracing.py` vide) — OpenCode.
9. Endpoints `app/api/v1/auth/` (login/me, JWT) inexistants — Antigravity.
10. Middleware auth global sur `/v1/*` — à décider puis tester (ce lot skippe à 404/401).
11. Routage imbriqué 404 sous FastAPI 0.141 (voir observation) — Antigravity.
