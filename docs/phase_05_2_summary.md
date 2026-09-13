# PHASE-05.2 — Résumé factuel (lot 1 : E2E avec DB réelle)

Phase active (`agent_workspace/CURRENT_PHASE.md`) : **PHASE-05 ✅ TERMINÉE (209 tests)**,
**PHASE-06 Quality & Confidence 🚀 À LANCER**. Ce lot initie les tests §33.2 avec vraie
DB PostgreSQL via testcontainers (réf. spec §33.2, roadmap §35 phase 5 : pgvector).

Point d'intégration Cursor : branche `agent/cursor/integration`, lot basé sur `cdf02ca`.
État de départ : 209 passed, 0 skipped. PRs PHASE-05 mergées : #24 (Codex domain),
#25 (Devin storage), #26 (OpenCode), #27 (Antigravity api).

## Zones couvertes par ce lot

`tests/integration/test_phase_05_2_e2e.py` : 6 tests, fixture module unique
`pg_urls` (un conteneur `postgres:16-alpine` partagé), helpers `_has_module()` /
`_has_symbol()` + `@pytest.mark.skipif(not DOCKER_AVAILABLE)`. Import
`testcontainers.community.postgres` (le chemin `testcontainers.postgres` est déprécié).

| Test | Résultat local (Docker 29.7.2 joignable) | Preuve réelle |
|---|---|---|
| `test_postgres_connector_real` | ✅ pass | `SELECT 1` via `app.storage.database.engine.create_engine` + cycle `discover` → `retrieve` → `inspect` → `health_check` → `metadata` du connecteur |
| `test_audit_writer_persistence` | ✅ pass | DB levée + contrat `write`/`list_events` (filtre `actor_id`, `audit_event_id`, `timestamp`) |
| `test_lineage_tracker_persistence` | ✅ pass | DB levée + `record`/`get_lineage` (ancestry transitive, descendants) |
| `test_health_aggregator_with_real_checks` | ✅ pass | `aggregate()` avec vrai check `SELECT 1` + check statique → `status: up`, 2 subsystems |
| `test_health_ready_endpoint` | ⏭️ skip | `app/api/v1/system/health_router.py` vide (0 octet), aucun symbole `router` |
| `test_source_repository_with_db` | ⏭️ skip | `app/storage/repositories/source_repository.py` vide (0 octet), aucun `SourceRepository` |

Sans Docker, les 6 tests skippent au marker (`Docker/testcontainers unavailable`).
Si le conteneur ne démarre pas, la fixture skippe (`conteneur postgres indisponible`).

## Dettes corrigées (constatées, non revendiquées comme livrées par ce lot)

- §33.2 PostgreSQL : premier test d'intégration contre vraie DB (auparavant aucun —
  `test_database_connection.py` et `test_repositories.py` sont des placeholders vides).
- Les contrats `AuditWriter.write`/`list_events`, `LineageTracker.record`/`get_lineage` et
  `HealthAggregator.register`/`aggregate` sont désormais exercés (en mémoire + DB levée).

## Nouvelles APIs exposées (utilisées par ce lot, livrées par les PRs PHASE-05)

- `app.governance.audit.audit_writer.AuditWriter.write` / `list_events`
- `app.provenance.lineage_tracker.LineageTracker.record` / `get_lineage`
- `app.observability.health_aggregator.HealthAggregator.register` / `aggregate`
- `app.storage.database.engine.create_engine` (URL `postgresql+asyncpg://`)
- `app.storage.search` : `VectorSearch`, `HybridSearch`, `FullTextSearch`

## Dettes restantes

1. `PostgresConnector` reste stub partiel (aucune requête réelle, dette PHASE-05/06 #1).
2. `AuditWriter` en mémoire, sans persistance (dette #3).
3. `LineageTracker` non persistant (dette #6).
4. `HealthAggregator` : aucun check enregistré par défaut dans l'app (dette #4) —
   ce lot injecte ses propres checks.
5. `app/api/v1/system/health_router.py` vide → endpoint ready à livrer (Antigravity).
6. `app/storage/repositories/` entièrement stub (dont `source_repository.py`) → Devin.
7. `app/storage/models/` stub sauf `base.py` → Devin.
8. Reporté : `readability_extractor.py` vide, ChunkSplitter approximatif, search stubs
   à listes vides, pas de tests pgvector avec vraie extension.
