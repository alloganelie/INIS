# PHASE-05 — Résumé factuel (lot 1 : E2E Knowledge Layer)

Phase active (`agent_workspace/CURRENT_PHASE.md`) : **PHASE-05 Knowledge Layer — 🚀 À LANCER**.
Objectif : information units, evidence, pgvector, recherche hybride, mémoire, provenance.
Référence spec : INIS_SPEC.md §11 (InformationUnit), §12 (cycle de vie), §16 (pgvector),
§17 (mémoire) ; tests §33, métriques §34.

Point d'intégration Cursor : branche `agent/cursor/integration`, lot basé sur `c25e2bc`
(`docs(phase): close PHASE-04.3, open PHASE-05`). État de départ : 169 passed, 0 skipped.

## Zones couvertes par ce lot

| Test | Zone observée | État constaté |
|---|---|---|
| `test_information_unit_imports` | `app/domain/entities/information_unit.py` | **fichier vide (0 octet) → skip** |
| `test_evidence_imports` | `app/domain/entities/evidence.py` | **fichier vide (0 octet) → skip** |
| `test_claim_imports` | `app/domain/entities/claim.py` | **fichier vide (0 octet) → skip** |
| `test_chunk_splitter_smoke` | `app/knowledge/chunking/chunk_splitter.py` | **fichier vide (0 octet) → skip** (tout `app/knowledge/` est stub) |
| `test_lineage_tracker_smoke` | `app/provenance/lineage_tracker.py` | **fichier vide (0 octet) → skip** (tout `app/provenance/` est stub) |
| `test_vector_search_imports` | `app/knowledge/search/vector_search` | **module inexistant → skip** (§16) |
| `test_hybrid_search_imports` | `app/knowledge/search/hybrid_search` | **module inexistant → skip** (§16.2) |
| `test_metrics_registry_smoke` | `app/observability/metrics.py` | **fichier vide (0 octet) → skip** (§34) |
| `test_evidence_endpoint_imports` | `app/api/v1/evidence` | **`__init__.py` + `router.py` vides → skip** |
| `test_conflicts_endpoint_imports` | `app/api/v1/conflicts` | **`__init__.py` + `router.py` vides → skip** |
| `test_metrics_endpoint_returns_dict` | `app/api/v1/system/metrics_router.py` | **fichier vide (0 octet) → skip** |
| `test_information_unit_provenance_invariant` | schéma §11 (`provenance` non vide) | **skip (InformationUnit absente)** |

## Tests ajoutés par ce lot

`tests/integration/test_phase_05_e2e.py` : 12 tests, helper `_has_module()` (pattern repris
de `test_phase_04_3_e2e.py`) + `_import_or_skip` / `_symbol_or_skip`. Résultat attendu :
12 skippés avec motif explicite — aucun comportement inventé, aucune zone revendiquée
comme livrée.

Couverture §33 à ce stade : aucune fumée §33.2/§33.3 spécifique Knowledge (pgvector,
recherche hybride, mémoire, provenance) n'est exécutable — les modules cibles sont des
stubs vides ou inexistants. Les 169 tests antérieurs restent verts.

## Dettes restantes (propriétaires pressentis)

1. Entités `InformationUnit` (§11), `Evidence`, `Claim` (§14) à implémenter — Codex.
2. `app/knowledge/` : chunking, extraction, embedding, normalisation à implémenter — Codex.
3. Recherche vectorielle + hybride §16 (table `embeddings`, pondération 0.6/0.4 §16.2) — Devin (pgvector) + Codex.
4. Mémoire §17 (`memory_lookup`, réutilisation) — Codex.
5. Provenance : `lineage_tracker.py`, `provenance_validator.py`, `transformation_recorder.py` vides — Codex.
6. Observabilité §34 : `metrics.py`, `metrics_endpoint.py`, `metrics_router.py` vides — OpenCode.
7. Endpoints `evidence` + `conflicts` (`router.py` vides) — Antigravity.
8. Reporté de PHASE-04.3 : `readability_extractor.py` vide ; PostgresConnector stub partiel ;
   AuditWriter en mémoire ; pas de tests avec vraie DB PostgreSQL.
