# Agent status

## PHASE-05.4 — Temporary ownership exception

Codex audited and repaired the Devin-owned `migrations/`,
`app/connectors/database/`, and `app/storage/search/` zones under the
human-authorized PHASE-05.4 exception. The Cursor-owned target
`tests/integration/test_phase_05_2_e2e.py` was absent from this branch. Codex
also corrected the Cursor-owned `tests/integration/test_postgres_real.py` fixture
to use the asyncpg driver under the same exception.

## PHASE-05.5 Lot A — Temporary ownership exception

Codex is authorized to resolve the assigned technical debt in Devin
(`migrations/`, `app/storage/`, `app/governance/`), Antigravity (`app/api/`),
Cursor (`tests/`), and OpenCode (`app/observability/`) zones for Lot A only.

Lot B extends this authorization to the PostgreSQL and web connector tests and
implementations, while retaining the same temporary cross-zone exception.

## Dettes techniques ouvertes

### SourceRepository (/v1/sources) — schéma divergent de la migration 0002

`app/api/v1/sources/repository.py` décrit un schéma `sources` qui ne correspond
pas à celui créé par `migrations/versions/0002_create_core_tables.py` :

| | `SourceRepository` (ORM/Core) | migration 0002 (PostgreSQL) |
|---|---|---|
| clé | `source_id` | `id` |
| colonnes | `name`, `description`, `trust_level`, `status`, `metadata` | `url`, `reliability_score`, `freshness`, `data_stage` |
| types | `String` / `JSON` | `Text` / `Float` / `JSONB` |

Le store créant sa propre table via `metadata.create_all`, il est correct sur
SQLite (schéma qu'il définit lui-même) mais divergent sur le schéma migré :
`INSERT ... source_id` échoue sur PostgreSQL. Le pipeline B4-bis écrit donc
`sources` en SQL direct, aligné sur la migration 0002, et ne passe pas par ce
repository.

**Action planée** : unifier en PHASE-12, au choix — migrer la table vers le
schéma du repository, ou réécrire le repository sur le schéma de la
migration. Découvert B4-bis, **non corrigé** à ce jour (hors périmètre).

### Autres dettes ouvertes (B4-bis)

- Cache L2 (PostgreSQL, table `cache_entries`) et L3 (pgvector) non câblés :
  seul le L1 in-process est branché sur `web_search` / `fetch_page`.
- `pytest-asyncio` reste en `asyncio_mode = "auto"` avec quelques tests marqués
  `@pytest.mark.asyncio` : nettoyage opportun.

## Dettes techniques ouvertes — post v2.0.0 (release 2026-09-27)

État de sortie : 1 428 tests verts, 1 skip explicite (`SERPER_API_KEY` absent),
`pytest -q` + les 4 checkers (`architecture`, `contracts`, `invariants`,
`backward_compat`) verts. Les 12 points ci-dessous sont **hors périmètre
v2.0.0** et planifiés PHASE-12 ; aucun ne bloque la release.

| # | Dette | Impact | Cible |
|---|---|---|---|
| 1 | Redis 7.2 EOL (février 2026) — image `redis:7-alpine` | sécurité/patching | migrer vers Valkey (PHASE-12) |
| 2 | Validateur mTLS absent (`app/security/certificates/` sans module) | authn service-à-service | implémenter (PHASE-12) |
| 3 | `SourceRepository` divergent de la migration 0002 (`source_id`/`id`) | cohérence SQLite↔Postgres | unifier les schémas (PHASE-12) |
| 4 | Helper de timestamp non centralisé (`datetime.now(UTC)` dispersé) | cohérence temporelle | `app/core/time.py` (PHASE-12) |
| 5 | `VersionStore` en mémoire, aucune table §27 dédiée | durabilité du versioning | persister §18.1 (PHASE-12) |
| 6 | §41.5 — cache **L2 PostgreSQL et L3 pgvector non câblés** (L1 OK, testé) | coût/latence | câbler L2/L3 (PHASE-12) |
| 7 | Python 3.11 EOL (oct. 2027) — matrice locale 3.11, CI 3.12 | support | migrer runtime 3.12 (PHASE-12) |
| 8 | `gitleaks` absent de la CI (token requis) | détection de secrets | job dédié (PHASE-12) |
| 9 | Rate limits Docker Hub — `docker/login-action` non configuré | fiabilité CI | login CI (PHASE-12) |
| 10 | Certificats TLS 47 jours — `cert-manager` à configurer en production | rotation | provisionner (prod, hors scope V1) |
| 11 | Overrides de dépendances — `httpx>=2.12.0` et `pydantic>=2.14.2` (PYSEC-2026-3844..3849, CVE-2026-65975/58203) **n'existent pas sur l'index** : floors positionnés au maximum publié (0.28.1 / 2.13.5) | CVE non couvertes upstream | relever dès publication (PHASE-12) |
| 12 | Sections SPEC ❌ / 🟡 de `docs/SPEC_COVERAGE.md` : `app/artifacts/**` + `app/api/v1/artifacts/` vides (§24.2, §24.3), `app/knowledge/embedding/` (§16) et `app/knowledge/enrichment/` (§12) absents, `tests/performance/**` vide (§41.13), fichiers de test vides (broker AMQP, cache Redis, connecteurs Excel/PDF/Web, `test_config.py`, `test_memory_checker.py`, `test_artifact.py`, `test_transformation.py`, factories) | couverture fonctionnelle | PHASE-12 |

Note : la tag `v1.0.0` a été créée sur `fce8c43` (`chore(release): add v1.0.0
refactoring report (C)`), commit de release retrouvé dans l'historique —
`git log v1.0.0..HEAD` fonctionne.

