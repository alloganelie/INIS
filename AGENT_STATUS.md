# Agent status

## Plan de conformité spec — source de vérité de l'avancement

L'audit exécuté le 2026-09-29 (spec ⇄ code, pas seulement lecture de docs) a montré que
l'ingestion de fichiers, l'interrogation PostgreSQL, la mémoire §16/§17, les transformations
et la livraison d'artefacts §24.2/§24.3 existent en **code + tests unitaires** mais ne sont
**pas branchés au pipeline** ni **exposés au client**. Le plan cochaable correspondant, avec
gates et pièges vérifiés, est dans **`docs/SPEC_CONFORMANCE_PLAN.md`**.

Conséquence de méthode : `docs/SPEC_COVERAGE.md` mesure « classe + test unitaire » et non
« capacité branchée et exposée » — la section §0 du plan définit les niveaux **N0/N1/N2** à
utiliser pour toute nouvelle ligne de couverture.

## Avancement — L0/L1 terminés le 2026-09-29 (`feat/conformance-v1`)

| Lot | Commit | Résultat mesuré |
|---|---|---|
| L0 — propreté, baseline, branche | `5c3c60f` | WIP pré-existant committé tel quel (114 fichiers) ; `pytest -q` → **1615 passed / 4 skipped** |
| L1 — artefacts §24.2/§24.3 de bout en bout | `7c1bba2` | `pytest -q` → **1687 passed / 4 skipped** ; 3 checkers + BC (0 breaking) OK ; `ruff` clean sur le lot ; `tsc --noEmit` OK |
| L2.1 — ingestion d'un fichier (upload multipart, MIME par contenu, S3, migration `0014`, PII §19.4) | `640cebd` | `pytest -q` → **1730 passed / 4 skipped** ; 4 checkers OK (0 breaking) ; `ruff` clean sur le lot ; `0014` up/down vérifiée ; image rebuild + routes montées dans un conteneur jetable |

L1 est **N2 sur le chemin nominal** : `required_output.format="xlsx"` produit un fichier réellement
stocké dans le conteneur S3, listé par `GET /v1/artifacts?request_id=`, et téléchargé avec un
`sha256` recalculé identique (`tests/integration/test_artifacts_object_storage.py`).
Détail des cases, preuves, décisions et du reste à faire : `docs/SPEC_CONFORMANCE_PLAN.md` §4 (encadrés L1
et L2) et §6 (journal). **Prochain lot : L2.2** — `app/agents/pipeline/tool_dispatch.py` (peupler
`ToolRegistry`, supprimer le stub `_ToolAdapter` qui fabrique du texte, C6/P1) puis **L2.3** (unités §11
extraites d'un document ingéré, `Dataset`, `Transformation` par étape).

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

---

## Remédiation `fix/pipeline-llm-synthesis` — 2026-09-28

Branche : `fix/pipeline-llm-synthesis` (base `3ac6c73`).

**État final : 1 592 tests verts, 2 skips d'environnement** (`INIS_RABBITMQ_URL`
absent → broker AMQP ; `SERPER_API_KEY` absent → recherche réelle). Les quatre
checkers (`architecture`, `contracts`, `invariants`, `backward_compat`) sont
verts. Le harnais E2E externe (conteneurs PostgreSQL/pgvector + Redis réels,
uvicorn, clés réelles) est à **63/63 PASS, 0 FAIL**.

### Défauts produit corrigés (pas seulement des tests)

| # | Défaut | § | Correctif |
|---|---|---|---|
| 1 | Les unités synthétisées par le pipeline partaient **sans `provenance`** : un client pouvait recevoir des affirmations non traçables | §0.2, §11 | `pipeline_runner` pose `source_id`/`method`/`derived_from` + schéma unité complet |
| 2 | Aucun composant ne pouvait reconstruire un colis §24.1 depuis les lignes persistées : une livraison persistée n'était pas re-livrable | §1, §24.1 | `InformationPackageRepository.assemble()` ; refuse un colis sans unité (donc sans provenance) |
| 3 | `audit_events.result` contenait le statut brut de livraison (`completed`) au lieu de `success`/`failure` | §20 | `pipeline_persistence` normalise |
| 4 | `CapabilityIndex` projetait ses `set` dans l'ordre du hash : `to_dict()` changeait à chaque processus (routage §6 et échanges §5.3 non reproductibles) | §5.3, §6 | projections triées ; test de stabilité |
| 5 | `object_uploader`/`object_downloader` importaient `aioboto3` au chargement du module : dépendance optionnelle transformée en import obligatoire | §4 | import paresseux → `InfrastructureError` |
| 6 | `app/domain/entities/memory_result.py` et `app/planning/memory_checker.py` manquaient (modules référencés, absents) | §7, §8 | implémentés |
| 7 | La route `POST /v1/requests/{id}/cancel` (§32) n'était couverte par **aucun** test | §32, §1.3 | `tests/api/test_request_cancel.py` (statut `CANCELLED`, idempotence, 404, drapeau runner, conservation du matériel déjà obtenu) |
| 8 | Une livraison annonçait `"artifacts": []` **en dur** (`pipeline_runner`) et aucun endpoint ne pouvait lister ou télécharger un fichier : le §24.2 n'était jamais construit, et `GET /v1/artifacts` n'existait pas alors que le frontend l'appelait | §24.1, §24.2, §24.3, §32 | L1 (`7c1bba2`) : générateurs CSV/JSON/XML/XLSX + refus PDF explicite, séquence `ART_{YYYY}_{SEQ6}` en base, migration `0013` (`request_id`, `created_at`, `artifact_id_sequences`), `ArtifactRepository`, `GET /v1/artifacts{,?request_id=,/{id},/{id}/download}`, câblage pipeline selon `required_output.format` |
| 9 | Le nom d'un fichier téléversé était **assaini avant** d'être classé (§19.4) : l'assainissement remplace `@` par `_`, donc un email dans le nom disparaissait avant de pouvoir être signalé comme PII | §19.4, §9.1 | L2.1 (`640cebd`) : la classification porte sur le nom **reçu**, le stockage garde le nom assaini ; verrouillé par `tests/security/test_upload_pii_classification.py` (le test qui a trouvé le défaut) |
| 10 | `python-multipart` était **installé mais non déclaré** : `UploadFile` ne pouvait pas être utilisé, et une image reconstruite sans la dépendance aurait refusé de démarrer | §4.1, §36.6 | L2.1 (`640cebd`) : déclaré dans `pyproject.toml` (`>=0.0.9`, CVE-2024-24762) ; vérifié par rebuild + `FastAPI.openapi()` en conteneur |

### Suites de tests remplies (lacune n°12 ci-dessus, partiellement soldée)

- `tests/performance/**` : plus vide — débit/latence séquentiels et queue,
  agents concurrents (identité des requêtes, unicité des ids, registre
  thread-safe), latence recherche vectorielle + hybride pgvector (§41.13).
- Tests d'intégration neufs : connecteurs PDF (pypdf, dégradation gracieuse sur
  fichier corrompu §25.1), Excel (openpyxl, `record_count` honnêtement à `None`),
  web (`mock` transport + providers live), Redis (cache L1 partagé, TTL délégué,
  fraîcheur §41.5), MinIO/S3, versioning, registre d'agents, broker AMQP.
- 15 factories `tests/factories/**` (identifiants toujours via `ULID`, §0.2/§0.3).
- Tests unitaires : `transformation`, `artifact`, `memory_checker`, `config`.

### Reste ouvert après cette remédiation

- **BC005 (29 warnings, non bloquants)** : deux index portent sur une table **préexistante** —
  `ix_artifacts_request_id` (`0013`, table `0005`) et `ix_documents_request_id` (`0014`, table
  `0002`), plus la contrainte `uq_documents_request_content` : ce sont les seuls cas où §41.14
  s'applique réellement. `CREATE INDEX CONCURRENTLY` est **interdit dans une transaction** et
  Alembic exécute les migrations en transactionnel (`INFO [alembic.runtime.migration] Will assume
  transactional DDL`) : l'activer casserait la migration. Les deux tables sont vides avant la
  livraison de leurs fonctionnalités (aucun writer n'existait), donc le verrou est sans effet ;
  à réévaluer si un index est ajouté plus tard sur une table volumineuse. Les 27 autres warnings
  indexent une table créée dans le **même `upgrade()`** : §41.14 ne s'y applique pas.
- **Dette n°12 (partie non soldée)** : `app/artifacts/**` + `app/api/v1/artifacts/` sont désormais
  **implémentés et branchés** (§24.2/§24.3, L1, commit `7c1bba2`) ; `app/knowledge/embedding/` (§16)
  et `app/knowledge/enrichment/` (§12) restent absents.
- **Dette n°6** : cache L2 (PostgreSQL) et L3 (pgvector) toujours non câblés ;
  le L1 est désormais testé contre Redis réel.
- **Secrets** : `start.bat` contient une clé `SERPER_API_KEY` et une clé OpenRouter
  en clair — **rotation à faire** (le fichier est ignoré par git).
- **Python local 3.11.9** alors que `pyproject.toml` cible `py312` : la CI fait foi.

### Comportement à connaître (documenté par les tests)

`POST /v1/requests` planifie l'exécution du pipeline en tâche de fond (§28) : créer
une requête déclenche donc un run réel, ce qui explique que le `pipeline_state`
d'une requête « vide » porte déjà du matériel.


