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

### 2026-10-04 — Horloge unique (dette D10)

- Added:
  - `app/core/time.py::utc_now()` — seule lecture de l'horloge de la plateforme
    (UTC, *timezone-aware*, microseconde ; aucune abstraction ajoutée).
- Changed:
  - 74 fichiers migrés : `datetime.now(UTC)` / `datetime.now(timezone.utc)`
    (114 occurrences) et 5 helpers locaux (`_utc_now`) remplacés par le helper
    central ; plus aucune génération directe dans `app/`.
- Tests:
  - `tests/unit/core/test_time.py` (7) dont une garde qui interdit la réapparition
    d'une lecture directe de l'horloge.
  - Suite complète Python 3.12 : **2815 passed / 5 skipped / 0 failed**.

### 2026-10-04 — Clôture produit (conformance V1)

- Added:
  - §9.2 : registre de plugins `inis.connectors` (`app/connectors/plugins.py`,
    groupe d'`entry_points` dans `pyproject.toml`), ADR 010, démonstration `ocr`
    par fixtures (capabilité déclarée, opérations refusées tant que le moteur absent).
  - Dette n°8 : gitleaks en CI (`.github/workflows/security.yml`) + `.gitleaks.toml`
    (placeholders `*.example` et fixture de test autorisés ; historique complet → 0 fuite).
  - `max_information_units_per_request` exposé dans `GET /v1/metrics → benchmarks` :
    les huit grandeurs §41.13 sont désormais toutes exposées.
- Changed:
  - `uvicorn[standard]` déclaré en **dépendance de production** : `pip install .`
    suffit pour servir l'API (l'image `docker/Dockerfile` démarre réellement).
  - `GET /v1/metrics` : suppression du repli silencieux (`except Exception: pass`) ;
    le payload §34 est toujours complet.
  - `tests/load/test_benchmarks.py` : assertions faibles remplacées par des
    garde-fous honnêtes (le vrai chemin est mesuré par `tests/load/harness.py`).
- Tests:
  - `tests/unit/connectors/test_plugin_discovery.py` (6) +
    `tests/integration/test_plugin_absent_degrades.py` (5).
  - `tests/unit/observability/test_metrics.py` : les 8 noms §41.13 exposés.

### 2026-09-27 — Version 2.0.0 (Release)

- Added:
  - E2E full-stack réel Phase 8.2 : `tests/integration/test_v2_full_stack.py`
    (Postgres + Redis + MinIO testcontainers, LLM + Web mockés uniquement).
  - Garde-fous Phase 8.3 : `scripts/check_invariants.py` (§0.2 inv.8/inv.15 + ULID),
    câblé dans la CI.
  - CI Phase 8.3 : job `python-tests` avec services Postgres/Redis/MinIO
    (MinIO pinné `quay.io/minio/minio:RELEASE.2024-10-13T13-34-11Z`).
- Changed:
  - Version projet portée à `2.0.0`.
- Tests:
  - `test_v2_full_stack` PASSED (20s, Docker local).

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

