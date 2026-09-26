# INIS — Changelog

Ce fichier conserve uniquement les changements importants de gouvernance, architecture ou contrats.

## Format

### YYYY-MM-DD — Version / Phase

- Added:
- Changed:
- Deprecated:
- Removed:
- Breaking changes:
- Migration:
- Tests:

### 2026-09-27 — Version 1.0.0 (Release)

- Added:
  - Primitives canoniques de hachage SHA-256 dans `app.core.hashing` (`sha256_hex`, `hash_record`, `verify_record`).
  - Connecteur `app.tools.web.web_search` intégrant `ProviderRouter` (§10).
  - Consommateur asynchrone de requêtes `app.workers.request_worker.RequestWorker` (§4.4).
  - Value object canonique `app.domain.value_objects.request_constraints` unifiant les contrats §7.
  - Tests unitaires complets sur `BudgetTracker`, `CostTracker`, `FallbackChain`, `QualityReporter`, `ABACEngine`, `Hashing`, `WebSearch`, et `RequestWorker`.
- Changed:
  - Remplacement de `datetime.utcnow()` par `datetime.now(UTC)` sur tout le projet.
  - Consolidation de `SearchProvider` vers son interface canonique dans `app.domain.interfaces.search_provider`.
  - Harmonisation des factories de connexion SQL via `app.storage.database.engine.create_engine_or_none`.
  - Aligné les schémas API wire `RequestConstraints` et `RequiredOutput` sur les valeurs par défaut du domaine.
- Removed:
  - Suppression de 232 modules vides (placeholders sans code).
  - Élimination des doublons `LoginRequest` et `LoginResponse` orphelins dans `app.api.v1.accounts.schemas`.
- Tests:
  - Suite de tests portée à 566 tests réussis (1 skip SERPER externe), 0 régression.

