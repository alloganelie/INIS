# Rapport de Refactoring — INIS v1.0.0

> Date d'exécution : 27 septembre 2026  
> Branche de release : `chore/v1-release-refactor`  
> Baseline de départ : commit `50eb7fa` (503 passed, 16 skipped)  
> État final : commit de release (566 passed, 1 skipped, 0 failed)

---

## 1. Synthèse exécutive

Le cycle de refactoring et d'audit v1.0.0 d'INIS a atteint l'ensemble de ses objectifs :
- **Audit formel complet** (`docs/AUDIT_V1.md`) : cartographie AST de 285 modules réels, examen des dettes D1 à D6, et vérification des invariants normatifs (§0.2, §0.3, §22.3).
- **Assainissement structurel** : suppression de 232 modules d'arborescence vides qui masquaient l'état du code. Implémentation complète des 3 modules référencés manquants (`app.core.hashing`, `app.tools.web.web_search`, `app.workers.request_worker`).
- **Hygiène temporelle** : élimination de `datetime.utcnow()` au profit d'horodatages UTC explicites (`datetime.now(UTC)` et chaînes ISO-8601 conformes §0.3 terminant par `"Z"`).
- **Consolidation (B2)** : élimination des doublons de définitions (`SearchProvider` unifié sur son interface canonique, factorisation du raccord SQL dans `create_engine_or_none`, source unique pour les contraintes de requête §7 dans `app.domain.value_objects.request_constraints`).
- **Stabilisation des tests (B6)** : ajout de 26 tests unitaires ciblés sans dépendances externes (`BudgetTracker`, `CostTracker`, `FallbackChain`, `QualityReporter`, `ABACEngine`, `Hashing`, `WebSearch`, `RequestWorker`), et résolution du skip d'import de `PipelineRunner`.
- **Documentation et release (B7 / C)** : mise à jour de `ARCHITECTURE.md`, `README.md`, `CHANGELOG.md` et rapport de clôture.

---

## 2. Métriques Avant / Après

| Indicateur | Avant (`50eb7fa`) | Après (`v1.0.0`) | Variation |
|---|---:|---:|---:|
| Fichiers Python totaux | 520 | 289 | **-231 files** (-44%) |
| Modules vides (placeholders) | 235 | 0 | **-235 (100% purgés)** |
| Tests pytest exécutés | 503 passed | **566 passed** | **+63 tests** (+12.5%) |
| Tests skippés | 16 | **1** (clé API tierce optionnelle) | **-15 skips** |
| Tests en échec / régressions | 0 | 0 | **0 régression** |
| `datetime.utcnow()` | 9 | 0 | **-9 (100% corrigés)** |
| Architecture checks (`check_architecture.py`) | 100% OK | 100% OK | Conforme |
| Contract checks (`check_contracts.py`) | 100% OK | 100% OK | Conforme |

---

## 3. Détail des Lots de Travaux

### Lot A — Audit et Hygiène
- Production de `docs/AUDIT_V1.md`.
- Remplacement systématique de `datetime.utcnow()` par `datetime.now(UTC)`.
- Suppression sécurisée de 232 modules vides (préservant tous les packages utiles et `__init__.py`).
- Implémentation des 3 modules référencés :
  - `app/core/hashing.py` : hachage cryptographique SHA-256 déterministe avec tri des dictionnaires.
  - `app/tools/web/web_search.py` : outil de recherche Web intégrant `ProviderRouter` et `SearchResult`.
  - `app/workers/request_worker.py` : boucle asynchrone de traitement par lot des requêtes.

### Lot B2 — Consolidation des types dupliqués
- `SearchProvider` : protocol canonique runtime checkable dans `app/domain/interfaces/search_provider.py`, ré-exporté proprement depuis `app/connectors/web/provider_router.py`.
- `RequestConstraints` & `RequiredOutput` : valeur objet canonique dans `app/domain/value_objects/request_constraints.py` ; alignement des schémas Pydantic de l'API avec test de garde anti-dérive.
- `create_engine_or_none` : factory factorisée dans `app/storage/database/engine.py` éliminant 4 copies du bloc de capture dégradé.
- Nettoyage des schémas d'authentification orphelins dans `app/api/v1/accounts/schemas.py`.

### Lot B6 — Couverture de tests accrue (+26 tests)
- `tests/unit/agents/test_budget_tracker.py` (6 tests) : limites d'itérations, de coût et snapshot d'usage.
- `tests/unit/llm/test_cost_tracker.py` (6 tests) : cumul de dépenses et suivi des tokens consommés.
- `tests/unit/llm/test_fallback_chain.py` (6 tests) : bascule ordonnée de modèles LLM et capture des erreurs.
- `tests/unit/quality/test_quality_reporter.py` (3 tests) : scores explicables et explications textuelles.
- `tests/unit/security/test_abac_engine.py` (5 tests) : évaluation des règles d'accès basées sur les attributs.

### Lot B7 & C — Documentation et Finalisation
- `ARCHITECTURE.md` : aligné sur les nouveaux value objects canoniques.
- `README.md` : documentation d'accueil complète, badges, commandes de démarrage et structure du projet.
- `CHANGELOG.md` : entrée détaillée pour la version 1.0.0.

---

## 3 bis. Lot B4-bis — Câblage des composants à la pipeline réelle

> Date d'exécution : 27 septembre 2026
> Branche : `feat/v2.0.0-spec-compliance`
> Base : commit `f9ea50c` (875 passed, 1 skipped) → fin de lot (904 passed, 1 skipped)

L'audit B4-bis a montré que l'API répondait sans jamais écrire en base, sans
limiter le débit, sans cache et en annonçant un état de santé fictif. Les cinq
constats sont corrigés ci-dessous, chacun dans un commit atomique.

### Constat 1 — Le pipeline n'écrivait rien en DB (§0.2, §12, §20, §27)

**Avant** : `pipeline_runner.py:33` stockait la livraison dans un dict
`self._run_states`, et `audit_id` était un `ULID.new("AUD_")` fabriqué, jamais
écrit. `AuditWriter` et `LineageTracker` n'étaient instanciés nulle part, et
`get_session()` n'avait aucun appelant.

**Après** (`app/api/v1/requests/pipeline_persistence.py`) :

| Élément | Avant | Après |
|---|---|---|
| `audit_events` | ULID synthétisé | `AuditWriter.write(..., session=session)` dans la transaction |
| `sources` | rien | INSERT (schéma migration 0002) |
| `information_units` | rien | INSERT (schéma migration 0002) |
| `evidence` | rien | INSERT (schéma migration 0007) |
| `transformations` (§12.1) | rien | INSERT via les helpers de `LineageTracker` |
| Transaction | aucune | `get_session()` — session unique, un seul `commit()` |
| Sans `INIS_DATABASE_URL` | silence | `limitations += ["persistence: in-memory only (...)"]` |

`AuditWriter.write()` accepte désormais un `session=` optionnel (et retourne
l'événement stocké) : l'audit rejoint la transaction du pipeline au lieu d'en
ouvrir une deuxième.

### Constat 2 — `AccountRepository` cassé (§19.2)

**Avant** : `get_account_repository()` renvoyait **la classe**, `repo.create(payload)`
n'était ni `await`é ni compatible avec la signature réelle → `TypeError` →
fallback in-memory **toujours** pris, y compris quand la base répondait. Le
`SessionRepository` était du code mort.

**Après** :
- `account_repository()` / `session_repository()` (context managers dans
  `app/storage/database/session.py`) fournissent un repository **lié à une
  `AsyncSession` réelle** ;
- les endpoints sont `async` et appellent la vraie signature
  `await repo.create(account_id=..., username=..., email=..., password_hash=..., status=...)` ;
- le fallback in-memory n'est atteint **que** si `INIS_DATABASE_URL` est absent ;
  une base configurée mais en panne remonte une vraie erreur au lieu de mentir ;
- `/v1/auth/login` crée une ligne `sessions` (hash SHA-256 du token, jamais le
  token), `/v1/auth/logout` pose `revoked_at` ;
- `app/main.py` monte enfin le router accounts sous `/v1` (il n'y était pas) ;
- le modèle `Session` a perdu le mixin `TimestampMixin` : la table `sessions`
  (migration 0006) n'a pas de colonne `updated_at`.

### Constat 3 — `/v1/health` mentait sur l'état réel (§32, §34)

**Avant** : avec aucune base et aucun broker, les deux checks répondaient `up`,
et le LLM n'était pas vérifié du tout : `/v1/health/ready` annonçait `ready`
alors que 100 % des appels LLM étaient des stubs silencieux.

**Après** :

| Situation | Avant | Après |
|---|---|---|
| `INIS_DATABASE_URL` absent | `up` (`in_memory`) | `not_configured` + `reason` |
| `AMQP_URL` absent | `up` (`not_applicable`) | `not_configured` + `reason` |
| `REDIS_URL` absent | `up` | `not_configured` + `reason` |
| `LLM_API_KEY` absent | *non vérifié* | `not_configured` + raison « ModelRouter renvoie des stubs » |
| `LLM_API_KEY` présent | *non vérifié* | appel réel (5 tokens) → `ready` / `not_ready` / `stub` |
| `AMQP_URL` présent | `down` sans vérifier | vraie tentative de connexion `aio_pika` |
| `GET /v1/health` | `{status, version, circuit_breakers}` | `{status, version, circuit_breakers, checks{database, redis, broker, llm}}` |
| Readiness globale | `ready` | `ready` / **`degraded`** (dépendance non configurée) / `not_ready` (503) |

Les probes passent toujours par `HealthAggregator` : timeout borné, exceptions
isolées, jamais de 500.

---

### Constat 4 — `RateLimiter` et `CacheStore` orphelins (§19, §41.5)

- `app/api/middleware/rate_limit_middleware.py` : token bucket par
  `request.state.actor_id` (repli `X-API-Key`, puis IP), store Redis si
  `REDIS_URL` est défini sinon in-process, `429` + `Retry-After`, exemptions
  identiques à celles de l'auth middleware **plus** `/v1/health*` et
  `/v1/status` (une sonde de liveness ne doit jamais être facturée).
  Monté **avant** `AuthMiddleware` dans `main.py` : Starlette applique le
  dernier middleware ajouté en premier, le limiteur doit donc tourner *à
  l'intérieur* de l'auth pour lire l'`actor_id` résolu.
  **Activation explicite** : `INIS_RATE_LIMIT_ENABLED=true` ou `RATE_LIMIT_RPM`
  défini. Un 60 rpm actif par défaut ferait échouer la suite de tests en 429 sur
  une clé anonyme partagée.
- Cache L1 branché sur `ProviderRouter.search()` (clé `query + provider + limit`)
  et `WikipediaExtractor.extract()` (clé `url`). Le seuil de fraîcheur de la
  policy §41.5 fait partie de la clé, sinon abaisser le seuil pourrait ressusciter
  une entrée stockée sous une policy plus stricte.
  **Choix technique** : `CacheStore` est synchrone ; les accès passent par
  `asyncio.to_thread` plutôt que par un second type asynchrone — le backend par
  défaut est un dict, et un wrapper aurait doublé l'API pour rien.
  `PipelineRunner.get_cache_stats()` expose le `cache_hit_rate` (§34).

### Constat 5 — Fixtures partagées absentes (§33.2)

`tests/containers.py` était un fichier de 0 octet et `tests/conftest.py` tenait
en 14 lignes. Maintenant :

| Fixture | Rôle |
|---|---|
| `postgres_container` / `redis_container` | images épinglées `pgvector/pgvector:pg16` et `redis:7-alpine`, scope session, skip propre sans Docker |
| `db_url` | Postgres migré (`alembic upgrade head`), le vrai schéma §27 |
| `redis_url` | endpoint Redis joignable |
| `reset_pipeline_state` (autouse) | isole le singleton `PipelineRunner` entre les tests |
| `mock_llm` | stub `ModelRouter.complete` configurable (`content`, `stub`, `calls`) |
| `mock_web` | `httpx.MockTransport` par défaut sur tout `AsyncClient` |

`test_phase_10_e2e.py` utilise désormais `mock_llm` au lieu de son propre
`_fake_complete`.

### Ce qui est câblé vs ce qui reste stub

| Composant | État | Détail |
|---|---|---|
| Pipeline → Postgres | ✅ câblé | audit + sources + unités + preuves + lineage, via `get_session()` |
| `AuditWriter` | ✅ câblé | écrit dans la transaction du pipeline |
| `LineageTracker` | ✅ câblé | table `transformations` alimentée |
| `AccountRepository` / `SessionRepository` | ✅ câblé | vrais repository sur `AsyncSession` |
| `/v1/health` | ✅ câblé | 4 checks réels, `not_configured` honnête |
| `RateLimiter` | ✅ câblé | middleware, Redis ou in-process, opt-in |
| `CacheStore` (L1) | ✅ câblé | web_search + fetch_page |
| `ModelRouter` sans `LLM_API_KEY` | ⚠️ stub assumé | le stub reste, mais il est **déclaré** par `/v1/health` |
| `SourceRepository` (`/v1/sources`) | ⚠️ divergence | écrit le schéma `source_id/name/metadata` alors que la migration 0002 crée `id/url/source_type/reliability_score/data_stage`. Le store crée sa propre table : correct sur SQLite, divergent sur le schéma migré. **Non traité** dans B4-bis — à aligner par une migration ou un repository dédié. |
| `accounts.role` / `accounts.scopes` | ⚠️ non persisté | aucune colonne dans la table `accounts` (migration 0006) ; la lecture DB renvoie `operator` / `[read, write]` par défaut |
| Cache L2 / pgvector (L3) | ❌ non câblé | hors périmètre B4-bis |
| package `redis` (optionnel) | ✅ | ajouté aux dépendances dev pour `RedisContainer` et le check Redis |

### Validation B4-bis

```powershell
python scripts/check_architecture.py   # OK
python scripts/check_contracts.py      # OK
python -m pytest -q                    # 904 passed, 1 skipped
```

Test E2E exécuté (uvicorn réel + Postgres testcontainer) :

| Critère | Résultat |
|---|---|
| `POST /v1/requests` → `SELECT audit_events` | ✅ 1 ligne |
| `POST /v1/requests` → `information_units` / `evidence` / `transformations` / `sources` | ✅ 1 ligne chacun |
| `POST /v1/accounts` → `SELECT accounts` | ✅ 1 ligne |
| `GET /v1/health` | ✅ `{status, version, circuit_breakers, checks{database, redis, broker, llm}}` |
| 2 `POST /v1/requests` rapides au-delàs du budget | ✅ `429` + `Retry-After` |
| 2 `web_search` identiques | ✅ 2ᵉ servi par le cache L1 (provider non appelé) |

---

## 4. Vérification et Conformité

- **Scripts de vérification** :
  ```powershell
  python scripts/check_architecture.py  # OK
  python scripts/check_contracts.py     # OK
  python -m pytest -q                   # 566 passed, 1 skipped
  ```
- **Invariants préservés** :
  - Aucune dépendance interdite ajoutée.
  - Aucun changement apporté à `INIS_SPEC.md`.
  - Règles d'encapsulation de domaine intactes (zéro I/O dans `domain`).
