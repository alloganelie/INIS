## PHASE-04 — Information Acquisition — ✅ TERMINÉE
Date : 2026-09-13 — Commit : <sha final> — Tests : 154

### Zones couvertes
| Zone | Agent | Fichiers clés |
|---|---|---|
| app/domain/entities/ | Codex | Source, Document, Dataset, SourceCandidate |
| app/connectors/base.py + files + database | Devin | SourceConnector, CSV/JSON/Excel/PG |
| app/connectors/api + web | OpenCode | REST + auth + providers |
| app/api/v1/sources + information | Antigravity | 6 endpoints |
| tests/integration + docs | OpenCode (rôle intégrateur) | Smoke E2E + phase_04_summary |

### Gate PHASE-04 — 6/6 ✅
- [x] Domain entities Source/Document/Dataset/SourceCandidate
- [x] Connecteurs CSV/JSON/Excel/PostgreSQL
- [x] Connecteurs REST + Web providers
- [x] Endpoints API sources + information
- [x] Tests E2E + résumé
- [x] CI verte + PR mergée

### Dettes techniques (PHASE-04.2)
1. `Dataset.schema` warning Pydantic → renommer en `dataset_schema`
2. `SourceConnector` redéclaré par OpenCode → converger vers `base.py`
3. `SearchResult` / `SearchProvider` redéclarés → converger vers domain
4. `CSVConnector.inspect()` compte la ligne vide finale → filtrer

---

## PHASE-05 — Knowledge Layer — 🚀 À LANCER

Objectif : information units, evidence, pgvector, recherche hybride, mémoire, provenance.

Référence : INIS_SPEC.md §11, §12, §16, §17.
## PHASE-04.2 — Corrections & Convergence — ✅ TERMINÉE
Date : 2026-09-13 — Commit : <sha final> — Tests : 158

### Corrections
1. `Dataset.schema` → `dataset_schema` (fix warning Pydantic) — Codex
2. `CSVConnector.inspect()` ignore lignes vides — Devin
3. `app/domain/entities/search_result.py` créé — Codex
4. Migration imports OpenCode → `base.SourceConnector` + `domain.SearchResult`

### Dette restante (reportée PHASE-04.3)
- `app/domain/interfaces/search_provider.py` vide → à créer
- Stubs Serper/Brave à `score=0.0` → normalisation réelle à venir
## PHASE-04.3 — Intégration réelle — ✅ TERMINÉE
Date : 2026-09-13 — Commit : <sha final> — Tests : 169

### Zones couvertes
| Zone | Agent | Fichiers clés |
|---|---|---|
| app/domain/interfaces/ | Codex | search_provider.py |
| app/governance/audit/ | Codex | audit_writer.py |
| app/core/ | Codex | logging.py (structlog) |
| app/connectors/database/ | Devin | postgres_connector.py |
| migrations/versions/ | Devin | 0002_create_core_tables.py |
| app/connectors/web/providers/ | OpenCode | serper/brave réels |
| app/connectors/web/extractors/ | OpenCode | trafilatura_extractor.py |
| app/api/v1/requests/ | Antigravity | progress_handler.py |
| app/api/v1/system/ | Antigravity | changelog_router.py |
| tests/integration/ | Intégrateur | test_phase_04_3_e2e.py |

### Gate PHASE-04.3 — 6/6 ✅
- [x] SearchProvider interface créée
- [x] AuditWriter + structlog
- [x] PostgresConnector réel (structure) + migration 0002
- [x] Providers Serper/Brave + Trafilatura
- [x] Progress endpoint + changelog
- [x] Tests E2E 169 passed, 0 skipped

### Dettes reportées (PHASE-05)
1. PostgresConnector reste stub partiel (pas de connexion réelle)
2. AuditWriter en mémoire (persistance à venir)
3. `readability_extractor.py` vide
4. Pas de tests d'intégration avec vraie DB PostgreSQL
5. Trafilatura non testée avec vraie lib (fallback regex testé)

---

## PHASE-05 — Knowledge Layer — 🚀 À LANCER

Objectif : information units, evidence, pgvector, recherche hybride, mémoire, provenance.

Référence : INIS_SPEC.md §11, §12, §16, §17.
## PHASE-05 — Knowledge Layer — ✅ TERMINÉE
Date : 2026-09-13 — Commit : <sha final> — Tests : 209

### Zones couvertes
| Zone | Agent | Fichiers clés |
|---|---|---|
| app/domain/entities/ | Codex | information_unit, evidence, claim |
| app/knowledge/chunking/ | Codex | chunk_splitter.py |
| app/provenance/ | Codex | lineage_tracker.py |
| migrations/versions/ | Devin | 0003_create_embeddings_and_search.py |
| app/storage/search/ | Devin | vector_search, hybrid_search, fulltext_search |
| app/observability/ | OpenCode | metrics, health_aggregator, metrics_endpoint |
| app/api/v1/evidence/ | Antigravity | schemas, router |
| app/api/v1/conflicts/ | Antigravity | schemas, router |
| app/api/v1/system/ | Antigravity | metrics_router |
| tests/integration/ | Intégrateur | test_phase_05_e2e.py |

### Gate PHASE-05 — 6/6 ✅
- [x] InformationUnit + Evidence + Claim (§11, §14)
- [x] ChunkSplitter + LineageTracker
- [x] Migration 0003 + pgvector (HNSW) + tsvector
- [x] Vector/Hybrid/FullText search
- [x] Observability (14 métriques §34)
- [x] Endpoints /v1/evidence, /v1/conflicts, /v1/metrics

### Dettes reportées (PHASE-06)
1. PostgresConnector reste stub (connexion réelle à faire)
2. Search classes restent stub (retournent listes vides)
3. AuditWriter in-memory (persistance à faire)
4. HealthAggregator sans checks enregistrés
5. ChunkSplitter approximatif (mots ~ tokens)
6. LineageTracker non persistant
7. Pas de tests avec vraie DB PostgreSQL

---

## PHASE-06 — Quality & Confidence — 🚀 À LANCER

Objectif : contrôles qualité, contradictions, scoring, matrice de confiance, fraîcheur.

Référence : INIS_SPEC.md §13, §14 (conflicts), §15.
## PHASE-05.2 → 05.4 — Consolidation & Fixes — ✅ TERMINÉE
Date : 2026-09-13 — Commit : <sha final> — Tests : 238 passed, 1 skipped

### Zones couvertes
| Zone | Agent | Fichiers clés |
|---|---|---|
| migrations/ + alembic.ini | Codex (exception) | env.py, 0002-0004 |
| app/connectors/database/ | Codex (exception) | postgres_connector (latency) |
| app/storage/search/ | Devin | vector, hybrid, fulltext |
| app/observability/ | OpenCode | health_aggregator, readability |
| app/api/v1/sources/ + system/ | Antigravity | repository, health/ready |
| tests/integration/ | Cursor + Codex | test_postgres_real, test_phase_05_2_e2e |

### Gate PHASE-05.2→05.4
- [x] Alembic fonctionne (upgrade head + downgrade base)
- [x] DATABASE_URL lue correctement
- [x] PostgresConnector opérationnel
- [x] Search classes réelles (vector/hybrid/fulltext)
- [x] Tests testcontainers PostgreSQL réels
- [x] 238 tests, 0 failed, 1 skipped (justifié)

### Exception documentée
Codex a couvert `migrations/`, `app/connectors/database/`, `tests/integration/` 
(zones Devin + Cursor) car Devin a échoué 2 fois sur Alembic.

### Dettes reportées (PHASE-06)
1. **SourceRepository** — décision architecturale : `app/storage/repositories/` (vide) 
   ou `app/api/v1/sources/repository.py` (existant) ? → aligner le test.
2. Schéma §27 partiel (claims, conflicts, artifacts manquants)
3. AuditWriter en mémoire (persistance DB)
4. HealthAggregator câblage lifecycle prod
5. DeprecationWarning `testcontainers.postgres` → `testcontainers.community.postgres`
## PHASE-05.5 — Nettoyage dettes techniques — ✅ TERMINÉE
Date : 2026-09-13 — Commit : `<sha final>` — Tests : 243 passed, 0 skipped, 0 failed

### Décision architecturale
`SourceRepository` conservé dans `app/api/v1/sources/repository.py`.
Placeholder `app/storage/repositories/source_repository.py` supprimé (règle 9).

### 7 dettes résolues
1. SourceRepository : placeholder supprimé, test E2E aligné
2. Schéma §27 : migration `0005_create_remaining_core_tables.py` (11 tables : claims, conflicts, artifacts, artifact_versions, artifact_lineage, agent_messages, execution_checkpoints, budget_usage, progress, access_policies, security_classifications)
3. AuditWriter : persistance DB (mode engine optionnel, rétrocompatibilité in-memory)
4. HealthAggregator : factory `make_default_checks(engine, redis_client, broker)`
5. `testcontainers.community.postgres` (au lieu de `testcontainers.postgres`)
6. PostgresConnector : test mode connecté réel
7. ReadabilityExtractor : test HTML riche

### Gate PHASE-05.5
- [x] Alembic upgrade + downgrade fonctionnels
- [x] 0 skip, 0 warning, 0 failed
- [x] 243 tests verts
- [x] Exception multi-zone documentée

### Exception documentée
Codex a touché 6 zones (Devin × 3, Antigravity × 1, OpenCode × 2, Cursor × 1).

---

## PHASE-06 — Quality & Confidence — 🚀 À LANCER

Objectif : contrôles qualité (§13), détection de contradictions (§14.4), modèle de confiance (§15).

Zones cibles :
- Codex : `app/domain/entities/conflict.py` + `app/quality/checks/`
- Devin : `app/quality/conflict/` + `app/quality/score/`
- OpenCode : `app/confidence/`
- Antigravity : `app/api/v1/quality/` + `app/api/v1/confidence/`
- Intégrateur : `tests/integration/test_phase_06_e2e.py`

Référence spec : `INIS_SPEC.md` §13, §14.4, §15.
## PHASE-06 — Quality & Confidence — ✅ TERMINÉE
Date : 2026-09-14 — Commit : <sha final> — Tests : 299 passed, 0 skipped

### Zones couvertes
| Zone | Agent | Fichiers clés |
|---|---|---|
| app/domain/entities/ | Codex | conflict.py |
| app/quality/checks/ | Codex | 11 checks (dont duplicates) |
| app/quality/conflict/ | Devin | detector, classifier, severity, resolver |
| app/quality/score/ | Devin | quality_scorer, quality_reporter |
| app/confidence/ | OpenCode (exception) | 7 dimensions + scorer + explainer |
| app/api/v1/quality/ + confidence/ | Antigravity | 7 endpoints |
| tests/integration/ | Intégrateur | test_phase_06_e2e.py |

### Gate PHASE-06
- [x] Conflict entity (§14.3)
- [x] 11 quality checks (§13.2)
- [x] Détection de contradictions (§14.4)
- [x] Score de qualité §13.3 (weighted_mean)
- [x] Modèle de confiance §15 (7 dimensions)
- [x] Endpoints /v1/quality + /v1/confidence
- [x] 299 tests, 0 failed, 0 skipped

### Exception documentée
OpenCode a couvert `app/confidence/` (zone Codex) sous accord explicite.

---

## PHASE-07 — Security — 🚀 À LANCER

Objectif : authentification (§19.2), autorisation RBAC+ABAC (§19.3), PII (§19.4), audit renforcé.

Référence : `INIS_SPEC.md` §19, §20, §41.9.
## PHASE-07 — Security — ✅ TERMINÉE
Date : 2026-09-21 — Commit : <sha final> — Tests : 365 passed, 13 skipped (Docker)

### Zones couvertes
| Zone | Agent | Fichiers clés |
|---|---|---|
| app/domain/entities/ | Codex | access_policy, security_classification |
| app/security/ | Devin | authn (jwt, api_key, mtls), authz (rbac, abac), pii, rate_limiting |
| app/governance/ | OpenCode (exception) | retention, gdpr_handler, pseudonymizer |
| app/observability/ | OpenCode | tracing |
| app/api/middleware/ + app/api/v1/auth/ | Antigravity | auth_middleware, login/refresh/me |
| app/main.py | Antigravity (07.4) | mount individuel sous-routers |
| tests/integration/ | Intégrateur | test_phase_07_e2e |

### Gate PHASE-07
- [x] AccessPolicy + SecurityClassification entities
- [x] Authn : JWT + API key + mTLS (stub)
- [x] Authz : RBAC + ABAC + policy evaluation
- [x] PII : détection + redaction + classification
- [x] Rate limiting : token bucket
- [x] Retention + GDPR handler
- [x] Tracing (TraceContext 32hex/16hex)
- [x] Middleware auth opt-in (`INIS_AUTH_ENABLED`)
- [x] Endpoints /v1/auth/login, /refresh, /me
- [x] 365 tests, 0 failed

### Exception documentée
OpenCode a couvert `app/governance/` (zone Devin) sous accord explicite.

### Dette technique majeure résolue
FastAPI 0.141.1 : `_IncludedRouter` paresseux cassait le montage agrégé
`v1_router`. Résolu par montage individuel des 13 sous-routers dans `app/main.py`.
Aucun impact performance.

---

## PHASE-08 — Frontend — 🚀 À LANCER

Objectif : React + Vite + TypeScript, 9 écrans §31.

Zone : `frontend/`
Référence : `INIS_SPEC.md` §31.
## PHASE-08 — Frontend — ✅ TERMINÉE
Date : 2026-09-21 — Commit : `33777d5` — Tests : 374 passed, 1 skipped (node_modules)

### Zones couvertes
| Zone | Agent | Fichiers clés |
|---|---|---|
| frontend/ (config + 9 écrans) | Antigravity | package.json, vite, 9 pages §31.1, 6 composants |
| frontend/src/types/ | Codex | domain.ts, api.ts, protocol.ts |
| frontend/src/mocks/ | OpenCode | fixtures.ts, server.ts (MSW) |
| docker/ + deploy/ | Devin | Dockerfile.frontend, nginx.conf, compose |
| tests/integration/ | Intégrateur | test_phase_08_e2e.py |

### Gate PHASE-08
- [x] React + Vite + TypeScript configuré
- [x] 9 écrans §31.1 (SubmitRequest, RequestStatus, Sources, ConfidenceMatrix, Conflicts, InformationUnits, AgentsSolicited, Traceability, RequestHistory)
- [x] 6 composants (Layout, AgentCard, ConfidenceBar, ConflictCard, EpistemicBadge, ProgressStepper, ProvenanceTree)
- [x] 9 clients API + types TS
- [x] Contexts (Auth, Trace) + hooks (useRequest, useSSE, useConfidence)
- [x] Mocks MSW pour dev/test
- [x] Docker frontend + nginx + compose
- [x] `npm run build` OK (116 modules, 267 kB)
- [x] `npm test -- --run` OK (1 passed)
- [x] 374 tests Python verts

### Exception documentée
- Codex a couvert `frontend/src/types/` (zone Antigravity) sous accord
- OpenCode a couvert `frontend/src/mocks/` (zone Antigravity) sous accord

### Dette résiduelle
Test `test_frontend_buildable` skip car `node_modules` non commité. À exécuter en CI avec `npm install` préalable.

---

## PHASE-09 — Orchestration E2E du pipeline agent — 🚀 À LANCER

Objectif : câbler les briques existantes (understanding, planning, execution, confidence) en un pipeline fonctionnel de bout en bout.

Zones cibles :
- Codex : `app/agents/understanding/`, `app/agents/decision/`, `app/agents/pipeline/`
- Devin : `app/planning/` (executor, iterations, budget usage)
- OpenCode : `app/llm/router/` (appels LLM réels), `app/llm/tasks/`, `app/llm/prompts/`
- Antigravity : `app/api/v1/requests/` (pipeline E2E endpoints)
- Intégrateur : `tests/integration/test_phase_09_e2e.py`

Référence : `INIS_SPEC.md` §7, §8, §22, §28.