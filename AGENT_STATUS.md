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
