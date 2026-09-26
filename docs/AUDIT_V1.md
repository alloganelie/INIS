# AUDIT V1 — INIS v1.0.0

> Audit réalisé sur `main @ 50eb7fa` (branche de travail `chore/v1-release-refactor`).
> Méthode : lecture directe du code + analyse AST (`ast`), pas de reprise d'assertion non vérifiée.
> Référence normative : `INIS_SPEC.md` v0.2.0 (⚠️ non lue intégralement, index par rôle uniquement).

---

## 1. Synthèse exécutive

| Indicateur | Valeur mesurée |
|---|---|
| Fichiers `.py` dans `app/` | **518** |
| dont vides (0 octet) | **279** (44 `__init__.py` + **235 modules placeholders**) |
| dont non vides | **239** |
| LOC `app/` (fichiers non vides) | **14 928** |
| Fichiers `.py` dans `tests/` | 193 (dont **88 vides**) |
| LOC `tests/` | 9 613 |
| Migrations Alembic | 6 (`0001` → `0006`), 0 placeholder vide |
| Suite de tests (baseline) | **503 passed, 16 skipped, 0 failed** (51,8 s) |
| Skips injustifiés | **1** (`test_phase_09_e2e.py::test_pipeline_runner_imports`) |
| Fichiers > 500 LOC | **1** (`app/api/v1/requests/pipeline_runner.py`, 700 LOC) |
| Fonctions > 50 LOC | **14** |
| `TODO`/`FIXME`/`HACK`/`NotImplementedError` dans `app/` | **0** (1 occurrence du mot « placeholder » dans une docstring) |
| `datetime.utcnow()` dans `app/` | **9** occurrences / 4 fichiers |
| Dépendances prohibées (`check_architecture`) | **0** |

**Constat structurant** : la dette majeure n'est pas le code écrit mais le **squelette d'arborescence**
— 235 modules Python vides (45 % des fichiers de `app/`) créés comme placeholders. C'est une
violation directe de `CODING_RULES.md` §5 (« Ne pas créer de fichiers `TODO`, `pass`, stubs ou faux
services uniquement pour satisfaire l'arborescence »).

---

## 2. Cartographie des modules (`app/`)

| Module | Fichiers | LOC |
|---|---:|---:|
| `app/api/` | 56 | 3 312 |
| `app/connectors/` | 35 | 2 489 |
| `app/llm/` | 26 | 1 369 |
| `app/storage/` | 76 | 1 163 |
| `app/messaging/` | 24 | 1 064 |
| `app/security/` | 24 | 917 |
| `app/quality/` | 26 | 844 |
| `app/agents/` | 19 | 733 |
| `app/planning/` | 8 | 539 |
| `app/domain/` | 100 | 514 |
| `app/observability/` | 6 | 468 |
| `app/confidence/` | 11 | 325 |
| `app/governance/` | 16 | 303 |
| `app/registry/` | 6 | 250 |
| `app/knowledge/` | 25 | 145 |
| `app/provenance/` | 4 | 123 |
| `app/workers/` | 5 | 113 |
| `app/core/` | 7 | 92 |
| `app/tools/` | 29 | 67 |
| `app/artifacts/` | 13 | 0 |
| racine `app/` | 2 | 98 |
| **TOTAL** | **518** | **14 928** |

Lectures clés :
- `app/domain/` (100 fichiers) et `app/storage/models/` (36 fichiers) sont **massivement vides** :
  la totalité des modèles ORM déclarés par l'architecture est absente, alors que les repositories
  qui devraient les utiliser sont eux aussi vides (19 fichiers).
- `app/artifacts/` = **13 fichiers, 0 LOC** : la livraison d'artefacts (§24/§33) n'existe pas en code.
- `app/tools/` = 29 fichiers pour 67 LOC : la quasi-totalité est vide.


---

## 3. Dettes vérifiées par lecture

Légende statut : ✅ **confirmée** · ⚠️ **partiellement inexacte** · ❌ **infirmée**

### D1 — mTLS validator ⚠️ *partiellement inexacte*
`app/security/authn/mtls_validator.py` (44 LOC) — **le validateur n'est pas vide**, il valide :
absence de `subject`, absence de `cn`, préfixe `AGENT_`. Mais :
- `self.trusted_cas` est **stocké et jamais utilisé** ;
- aucune vérification de chaîne, d'émetteur, de signature, de date d'expiration ou de révocation ;
- la docstring annonce « stub for V1 ».
**Dette réelle** : validation cryptographique absente → risque d'usurpation d'identité inter-agents.

### D2 — PostgresConnector read/write ⚠️ *partiellement inexacte*
`app/connectors/database/postgres_connector.py` (212 LOC) :
- `discover` / `retrieve` / `inspect` / `health_check` / `metadata` **sont implémentés** ;
- **aucune méthode d'écriture n'existe** → le volet « write » est **absent**, pas stub ;
- `_get_engine()` retourne `None` en cas d'échec de connexion et les appelants fabriquent alors
  **des données factices** (`data=f"SELECT * FROM {table_name} LIMIT 100"`). C'est un **fallback
  silencieux** : l'appelant reçoit un `RawSource` crédible et **aucune erreur n'est levée**.
- `retrieve` construit le SQL par f-string ; la protection repose uniquement sur
  `_validate_table_name()` (regex), le `LIMIT` est figé à 100 et non configurable.

### D3 — Rate limiting in-memory ✅ *confirmée*
`app/security/rate_limiting/rate_limit_store.py` : `self.buckets: Dict[str, Tuple[float,float]]`
en mémoire process. `RateLimiter` (token bucket) est correct mais **non partagé entre instances** :
en déploiement multi-pods, la limite est multipliée par le nombre de réplicas. Aucun backend Redis.
De plus, l'API est **synchrone** alors que la couche I/O INIS est asynchrone.

### D4 — LineageTracker non persistant ⚠️ *partiellement inexacte*
`app/provenance/lineage_tracker.py` (123 LOC) possède **déjà** : `record()` avec persistance
(`_persist_record` → INSERT dans `transformations`), `load_from_db()` et des tests unitaires.
**Dette réelle résiduelle** :
1. persistance **fire-and-forget** (`create_task`) : les tâches sont stockées dans
   `self._persistence_tasks` mais **jamais attendues ni exposées** → perte silencieuse possible ;
2. hors boucle événementielle, les enregistrements vont dans `_pending_records` **et n'en sortent
   jamais** (pas de `flush()` / `aclose()`) ;
3. `_persist_record` insère `input_ids`/`output_ids` (listes Python) sans `CAST` : dépend du type
   réel de la colonne en base ;
4. `record()` sans engine ne signale pas l'absence de persistance.

### D5 — ChunkSplitter : mots ≈ tokens ✅ *confirmée*
`app/knowledge/chunking/chunk_splitter.py` — `_token_count()`, `_overlap_sentences()` et
`_truncate_sentence()` comptent `str.split()`, c'est-à-dire des **mots**. La découpe est
sentence-aware et correcte, mais l'unité n'est pas le token du modèle d'embedding : un texte de
512 « tokens » peut en consommer ~1,3× plus → dépassement de fenêtre. Aucune documentation de
l'approximation, aucun point d'injection d'un compteur réel.

### D6 — `test_pipeline_runner_imports` skip ✅ *confirmée*
`tests/integration/test_phase_09_e2e.py:129-144` cherche `PipelineRunner` dans
`app.planning.pipeline_runner` et `app.agents.pipeline.pipeline_runner`, et `RequestWorker` dans
`app.workers.request_worker`. Or le runner réel est
**`app/api/v1/requests/pipeline_runner.py::PipelineRunner`** (700 LOC). Les trois chemins testés
n'existent pas/vides → **skip permanent** : le test ne peut jamais réussir.

### D7 — `DeprecationWarning` datetime.utcnow ✅ *confirmée (app/)*
9 occurrences dans 4 fichiers de `app/` :
`app/messaging/protocol/envelope_builder.py:95`, `app/registry/agent_registry.py:61,145,153,161`,
`app/workers/heartbeat_worker.py:44,98` (+ 2 docstrings à mettre à jour).
7 occurrences supplémentaires dans `tests/`.

### D8 — Stubs dans `app/storage/search/` ❌ *infirmée / requalifiée*
`fulltext_search.py` (64), `vector_search.py` (73), `hybrid_search.py` (83) sont **réellement
implémentés** (pgvector `<=>`, `ts_rank`, fusion pondérée 0.6/0.4 conforme §16.2). Dettes réelles :
- `_get_engine()` **dupliqué à l'identique dans 4 classes** (les 3 recherches + `PostgresConnector`) ;
- `except Exception: return None` → **une recherche en échec renvoie `[]`** : un incident pgvector
  est indiscernable d'une absence de résultat ;
- `hybrid_search.search` dépasse 50 LOC (51).

### D9 — `test_frontend_buildable` ❌ *infirmée*
`node_modules` **est présent** dans cet environnement et `npm run build` s'exécute puis passe :
**aucun skip** sur ce test dans la baseline.

### D10 — Doublons `SourceConnector` / `SearchResult` ⚠️ *partiellement inexacte*
- `SourceConnector` : **une seule** définition (`app/connectors/base.py`) → déjà consolidé.
- `SearchResult` : **une seule** définition (`app/domain/entities/search_result.py`) → déjà consolidé.
- **Doublons réels détectés** (collisions de nom de classe) :

| Classe | Emplacement A | Emplacement B | Verdict |
|---|---|---|---|
| `SearchProvider` | `app/domain/interfaces/search_provider.py` (canonique) | `app/connectors/web/provider_router.py` (copie locale) | **à fusionner** |
| `LoginRequest` | `app/api/v1/auth/schemas.py` | `app/api/v1/accounts/schemas.py` | **à fusionner** (contrat identique) |
| `AgentIdentity` | `app/registry/agent_registry.py` | `app/api/v1/agents/schemas.py` | **à unifier** |
| `RequestConstraints` | `app/agents/understanding/request_parser.py` | `app/api/v1/requests/schemas.py` | **à unifier** |
| `RequiredOutput` | `app/agents/understanding/request_parser.py` | `app/api/v1/requests/schemas.py` | **à unifier** |
| `SourceCandidate` | `app/connectors/base.py` (dataclass connecteur) | `app/domain/entities/source_candidate.py` (pydantic) | **à documenter** — sémantiques distinctes, pas une duplication |
| `Account` | `app/domain/entities/account.py` | `app/storage/models/account.py` | **légitime** — entité vs ORM |
| `Session` | `app/domain/entities/session.py` | `app/storage/models/account.py` | **légitime** — entité vs ORM |

### D11 — TODO/FIXME/placeholders ⚠️ *partiellement inexacte*
- **0** `TODO`, `FIXME`, `HACK`, `XXX`, `NotImplementedError` dans `app/` : ce point de dette est
  **infirmé**.
- Le placeholder réel, ce sont les **235 modules vides** (cf. §5).
- Docstring obsolète dans `app/connectors/web/provider_router.py` (« `app/domain/interfaces/
  search_provider.py` is still an empty placeholder ») : **faux**, le fichier contient 15 LOC.



---

## 4. Violations potentielles de `§0.2` (aucun fait sans `source_id`)

Analyse par lecture des points de création d'information :

| Emplacement | Constat |
|---|---|
| `app/api/v1/requests/pipeline_runner.py` (fin de `run`) | ✅ Conforme : les `findings` sans `source_id` vérifié sont déclassés en hypothèses, statut global `INSUFFICIENT_EVIDENCE` si aucun finding vérifié, limitation explicite ajoutée. Testé (`test_pipeline_marks_unsourced_facts_as_hypothesis`). |
| `app/quality/` (`fact_extractor`, score) | ✅ `source_id` propagé. |
| `app/llm/` | ✅ Aucune écriture d'`InformationUnit`/`Claim` depuis le LLM ; le routeur ne produit que du texte (`LLMResponse`). Conforme à §22.3. |
| `app/connectors/database/postgres_connector.py` | ⚠️ **Point de vigilance** : en mode dégradé, `retrieve()` fabrique un `RawSource` factice portant un `source_id` de forme valide. Le fait n'a **pas** de source réelle mais ressemble à un fait sourcé. **À corriger** (D2). |
| `app/storage/search/*` | ⚠️ Renvoie `[]` en mode dégradé (aucun fait fabriqué) → pas de violation §0.2, mais perte du signal d'erreur. |
| `app/provenance/lineage_tracker.py` | ✅ `_persistence_record` horodate en UTC et conserve les identifiants. |

Aucune violation franche de §0.2 dans le chemin nominal. Un risque de **faux `source_id`** subsiste
dans le mode dégradé du connecteur Postgres.

---

## 5. Placeholders vides et modules orphelins

`app/` contient **235 modules non-`__init__` de 0 octet**. Analyse de référence (recherche du chemin
pointé complet dans tout le dépôt, chaînes de caractères de tests et docs incluses) :

| Catégorie | Nombre | Décision |
|---|---:|---|
| Référencés par du code de production ou un test | **3** | à traiter un par un (ci-dessous) |
| Non référencés nulle part | **232** | **suppression** (interdits par `CODING_RULES` §5) |

Les 3 modules vides référencés :

| Module | Référencé par | Traitement |
|---|---|---|
| `app/core/hashing.py` | `docs/phase_11_wave1_summary.md` (documenté comme vide) | **implémenter** (`sha256`, `before_hash`/`after_hash` conformes `ARCHITECTURE.md`) |
| `app/tools/web/web_search.py` | `docs/phase_10_summary.md` (documenté comme vide) | **implémenter** (outil `web_search` du planner, réutilise `ProviderRouter`) |
| `app/workers/request_worker.py` | `tests/integration/test_phase_09_e2e.py:138` | **implémenter** `RequestWorker` (délégation au `PipelineRunner`), ce qui lève un skip injustifié |

Modules orphelins **non vides** : `app/core/logging.py` (1 226 o) n'est importé par personne —
`structlog` est pourtant déclaré en dépendance. À brancher ou à documenter.

Tests vides : **88 fichiers `test_*.py` de 0 octet** (dont 14 scénarios `tests/agentic/`).
Ils sont collectés par pytest mais n'exécutent rien.

---

## 6. Taille des fichiers et des fonctions

Fichiers > 500 LOC (1) :
- `app/api/v1/requests/pipeline_runner.py` — **700 LOC**, `run()` = **617 LOC** (lignes 81-697).

Fonctions > 50 LOC (14) :

| Lignes | Emplacement | Fonction |
|---:|---|---|
| 617 | `app/api/v1/requests/pipeline_runner.py:81` | `PipelineRunner.run` |
| 132 | `app/api/middleware/auth_middleware.py:137` | `dispatch` |
| 121 | `app/messaging/protocol/envelope_validator.py:38` | `validate` |
| 96 | `app/planning/plan_executor.py:39` | `execute` |
| 94 | `app/llm/router/model_router.py:133` | `complete` |
| 86 | `app/api/v1/system/health_router.py:38` | `get_health_ready` |
| 84 | `app/messaging/protocol/envelope_builder.py:58` | `build` |

---

## 7. Baseline de la suite de tests

```
503 passed, 16 skipped in 51.83s
```

Répartition des 16 skips :

| Cause | Nombre | Justification |
|---|---:|---|
| Docker / testcontainers indisponible (`test_phase_05_2_e2e.py`) | 6 | environnement légitime |
| `test_postgres_real.py` (Docker) | 7 | environnement légitime |
| `SERPER_API_KEY` absent (`test_phase_10_e2e.py`) | 1 | environnement légitime |
| Docker daemon (`test_phase_11_wave1_e2e.py`, migration 0006) | 1 | environnement légitime |
| **Chemin de module erroné (`test_phase_09_e2e.py`)** | **1** | ❌ **injustifié — à corriger** |

⚠️ Le brief de mission annonçait « 517 passed, 2 skipped » pour `21ce2d9` ; la mesure réelle à
`50eb7fa` est **503 passed, 16 skipped**. L'écart est dû aux tests conditionnés à Docker/SERPER
(14 skips d'environnement ici) et à l'évolution de la suite entre les deux commits.

---

## 8. Autres constats

1. **Erreurs** : `app/core/errors.py` existe et est utilisé, mais le connecteur Postgres et les
   recherches absorbent les exceptions (`except Exception`) au lieu d'utiliser la hiérarchie INIS.
2. **Signatures async** : `PostgresConnector`, `HealthAggregator`, `LineageTracker` sont cohérents.
   En revanche `RateLimitStore`/`RateLimiter` sont **synchrones** alors que le reste de la couche I/O
   est asynchrone → rupture d'homogénéité à corriger lors du passage Redis.
3. **Version** : `pyproject.toml` = `0.1.0`, `health_router.get_health()` renvoie `"0.1.0"` en dur
   et `PostgresConnector.metadata()` renvoie `"1.0.0"` en dur → **incohérence** à unifier vers `1.0.0`.
4. **`app/observability/health_aggregator.py`** (215 LOC) est implémenté et testé mais **non câblé**
   dans `app/api/v1/system/health_router.py`, qui réimplémente sa propre logique de readiness
   (86 LOC dans `get_health_ready`) → duplication de logique de santé.

---

## 9. Plan de remédiation retenu

| Étape | Contenu | Commit |
|---|---|---|
| A | Audit | `docs(audit): ...` |
| B1 | Hygiène : `datetime.utcnow` → `datetime.now(UTC)` (app + tests), imports inutilisés, docstring obsolète | `refactor(hygiene): ...` |
| B2 | Consolidation : `SearchProvider`, `LoginRequest`, `AgentIdentity`, `RequestConstraints`/`RequiredOutput`, factorisation `_get_engine` | `refactor(consolidation): ...` |
| B3 | Placeholders : suppression des 232 modules vides + implémentation des 3 référencés | `chore(cleanup): ...` |
| B4 | Stubs : PostgresConnector (fin des fallbacks factices + écriture), RateLimiter Redis (async), LineageTracker flush, HealthAggregator câblé, fix `test_pipeline_runner_imports` | `fix(stubs): ...` |
| B5 | Qualité : éclatement de `pipeline_runner.py`, extraction des helpers | `refactor(api): ...` |
| B6 | Tests : +20 tests sur les modules refactorés | `test: ...` |
| B7 | Docs : `ARCHITECTURE.md`, `API_REFERENCE.md`, `README.md`, `CHANGELOG.md`, docstrings | `docs: ...` |
| C | Release : `version = 1.0.0`, `REFACTOR_REPORT.md` | `chore(release): ...` |

**Règles appliquées** : aucune régression (suite verte après chaque commit), aucune nouvelle
fonctionnalité, `INIS_SPEC.md` non modifié, §0.2 / §22.3 / §0.3 respectés, aucune nouvelle dépendance
sans justification.

| 83 | `app/agents/pipeline/pipeline_coordinator.py:74` | `run` |
| 67 | `app/connectors/web/extractors/trafilatura_extractor.py:33` | `extract` |
| 59 | `app/storage/object_storage/object_uploader.py:85` | `_upload_multipart` |
| 55 | `app/connectors/web/extractors/readability_extractor.py:38` | `extract` |
| 53 | `app/api/v1/auth/router.py:43` | `login` |
| 51 | `app/storage/search/hybrid_search.py:33` | `search` |
| 51 | `app/planning/iteration_manager.py:65` | `should_continue` |
