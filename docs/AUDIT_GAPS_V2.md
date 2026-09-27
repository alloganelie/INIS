# INIS v2.0.0 — Audit des écarts de conformité à INIS_SPEC.md v0.2.0

> Date : 27 septembre 2026
> Branche : `feat/v2.0.0-spec-compliance`
> Base auditée : `fce8c43` (v1.0.0)
> Méthode : lecture directe du code, inventaire AST, vérification d'importabilité, exécution de la suite.
> Baseline mesurée : **566 passed, 1 skipped, 0 failed**.

---

## 0. Verdict exécutif

| Axe | v1.0.0 | Cible v2.0.0 |
|---|---:|---:|
| Sections SPEC entièrement conformes | 18 / 41 | 41 / 41 |
| Sections partielles | 14 / 41 | 0 |
| Sections absentes | 9 / 41 | 0 |
| Outils §21 implémentés | 2 / 35 | 35 / 35 |
| Scénarios agentiques §33.3 couverts | 0 / 10 | 10 / 10 |
| Métriques §34 exposées | 14 / 14 (non instrumentées) | 14 / 14 |
| Tables §27 présentes en migration | 20 / 28 | 28 / 28 |
| Fichiers de test vides (0 octet) | **87** | 0 |
| Répertoires `app/` sans aucun module | **19** | 0 |

**Cause racine de l'écart** : la v1.0.0 a traité le *squelette* (232 modules placeholders supprimés),
mais 87 fichiers de test et 19 répertoires applicatifs sont restés vides. L'arbre de la SPEC
(§21, §28, §33.3, §41) a été documenté dans `ARCHITECTURE.md` sans implémentation correspondante.

---

## 1. Statut §1 → §41

Légende : ✅ **Conforme** · 🟡 **Partiel** · ❌ **Absent**

### Fondations

| § | Sujet | Statut | Fichier(s) | Preuve | Effort |
|---|---|---|---|---|---|
| §0.2 | Invariants (source_id / transformation_id) | ✅ | `app/domain/entities/information_unit.py:35` | `tests/unit/domain/*` | — |
| §0.3 | Préfixes ULID | ✅ | `app/core/constants.py`, `app/domain/value_objects/ulid.py` | `tests/unit/core/test_identifiers.py` | — |
| §1.1 | Périmètre fonctionnel V1 | 🟡 | voir §1.1 détaillé | `tests/unit/connectors/*` | M |
| §2 | Positionnement multi-agents | ✅ | `app/registry/agent_registry.py` | `tests/unit/registry/test_agent_registry.py` | — |
| §3 | Composants obligatoires | 🟡 | 19 répertoires vides | inventaire §3 | M |
| §4 | Stack technique | ✅ | `pyproject.toml` | — | — |
| §5 | Protocoles inter-agents | ✅ | `app/messaging/protocol/envelope_*.py` | `tests/unit/messaging/*` | — |
| §6 | Agent Registry | ✅ | `app/registry/agent_registry.py` | `tests/unit/registry/test_agent_registry.py` | — |
| §7 | Modèle de demande | ✅ | `app/domain/value_objects/request_constraints.py` | `tests/unit/api/test_request_schema_defaults.py` | — |
| §8 | Planification autonome | ✅ | `app/planning/plan_builder.py`, `plan_executor.py` | `tests/unit/planning/*` | — |

### Cœur métier

| § | Sujet | Statut | Fichier(s) | Preuve | Effort |
|---|---|---|---|---|---|
| §9 | Connecteurs de sources | 🟡 | `app/connectors/base.py` + 10 connecteurs | `tests/unit/connectors/*` | S |
| §10 | Recherche Web | ✅ | `app/connectors/web/provider_router.py` | `tests/unit/connectors/test_provider_router.py` | — |
| §11 | InformationUnit (28 champs) | ✅ | `app/domain/entities/information_unit.py` | `tests/unit/domain/*` | — |
| §12 | RAW → DERIVED + transformation_id | 🟡 | `app/provenance/lineage_tracker.py:74` | `tests/unit/provenance/test_lineage_tracker.py` | S |
| §13 | Qualité des données | ✅ | `app/quality/checks/*` (10 modules) | `tests/unit/quality/*` | — |
| §14 | Preuves et contradictions | ✅ | `app/quality/conflict/*` | `tests/unit/quality/test_conflict_detector.py` | — |
| §15 | Modèle de confiance | ✅ | `app/confidence/dimensions/*` (7 dimensions) | `tests/unit/confidence/*` | — |
| §16 | Recherche vectorielle pgvector HNSW | 🟡 | `app/storage/search/vector_search.py` | `tests/integration/test_pgvector.py` (vide) | M |
| §17 | Mémoire | ❌ | aucun `memory_lookup` | — | M |
| §18 | Gouvernance de la donnée | ✅ | `app/governance/retention/retention_enforcer.py` | `tests/unit/governance/*` | — |
| §19 | Sécurité | ✅ | `app/security/**` | `tests/unit/security/*` | — |
| §20 | Audit et observabilité | 🟡 | `app/observability/tracing.py` | `tests/unit/observability/*` | M |
| §21 | Outils internes (35) | ❌ | 2 / 35 | voir §4 | L |
| §22 | LLM et Model Router | ✅ | `app/llm/router/model_router.py` | `tests/unit/llm/*` | — |
| §23 | Exécution sécurisée | ✅ | `app/agents/runtime/state_machine.py` | `tests/unit/agents/*` | — |
| §24 | Contrat de livraison | 🟡 | `app/agents/decision/partial_result_packager.py` | `tests/api/test_pipeline_e2e.py` | M |
| §25 | Incertitude et échecs | ✅ | `app/agents/decision/termination_evaluator.py` | `tests/unit/agents/*` | — |
| §26 | Architecture des services | 🟡 | `app/workers/*` (2 workers) | `tests/unit/workers/*` | S |
| §27 | Tables obligatoires (28) | 🟡 | 20 / 28 en migration | `tests/integration/test_migrations.py` (vide) | M |
| §28 | Cycle complet (22 étapes) | 🟡 | `app/agents/pipeline/pipeline_coordinator.py` | `tests/integration/test_pipeline.py` | M |
| §29 | Communication inter-agents | ✅ | `app/messaging/amqp/*` | `tests/unit/messaging/*` | — |
| §30 | Délégation vers un autre agent | 🟡 | `app/agents/decision/delegation_decider.py` | aucun test E2E | M |
| §31 | Frontend minimal | 🟡 | `frontend/` (fichiers vides) | `tests/integration/test_phase_08_e2e.py` | S |
| §32 | API interne / externe | ✅ | `app/api/v1/**` | `tests/api/*` | — |
| §33 | Tests obligatoires | ❌ | 87 fichiers de test vides | voir §5 | L |
| §34 | Observabilité (14 métriques) | 🟡 | `app/observability/metrics.py` (14 noms, 0 instrumentation) | `tests/api/test_evidence_conflicts.py:135` | M |

### Production (§41) — quasi intégralement absent

| § | Sujet | Statut | Fichier(s) | Preuve | Effort |
|---|---|---|---|---|---|
| §41.1 | Lifecycle requêtes longues | 🟡 | `app/api/v1/requests/progress_handler.py` (snapshot synthétique) | `tests/api/test_progress_changelog.py` | M |
| §41.2 | Quotas et facturation | ❌ | — | — | M |
| §41.3 | i18n et multilinguisme | ❌ | — | — | M |
| §41.4 | Credential vault | ❌ | `app/security/vault/` vide | — | M |
| §41.5 | Cache L1/L2 + invalidation | ❌ | `app/storage/cache/` vide | — | M |
| §41.6 | Chunked datasets | ❌ | — | — | M |
| §41.7 | Désinformation | ❌ | `app/quality/suspicion/` vide | — | M |
| §41.8 | Retry + circuit breaker | 🟡 | `RetryPolicy` existe (`dead_letter_handler.py:27`) ; **CircuitBreaker absent** | — | M |
| §41.9 | GDPR complet | 🟡 | `GDPRHandler` existe ; portabilité/rectification absents | `tests/unit/governance/test_gdpr_handler.py` (vide) | M |
| §41.10 | Topologie de délégation | ❌ | — | — | M |
| §41.11 | Compatibilité protocole | ❌ | version codée en dur `"1.0"` dans 3 fichiers | `tests/unit/messaging/test_envelope_validator.py:48` | M |
| §41.12 | Observabilité LLM | 🟡 | `app/llm/tracing/llm_trace_writer.py` existe, non câblé au pipeline | `tests/integration/test_phase_09_e2e.py:126` | S |
| §41.13 | Tests de charge | ❌ | `tests/performance/*` vides | — | M |
| §41.14 | Déploiement safe | ❌ | pas de `check_backward_compat.py` | — | S |
| §41.15 | Doc auto-générée | 🟡 | `/v1/changelog` OK ; `/v1/agents/{id}/schema` absent | `tests/api/test_progress_changelog.py` | S |

### §1.1 détaillé — features du périmètre V1

| Feature SPEC | Statut | Preuve |
|---|---|---|
| Recherche Web | ✅ | `app/tools/web/web_search.py` |
| Connecteurs fichiers (csv/xlsx/json/xml/pdf/docx) | 🟡 | `excel_connector.py:16` se déclare « stub » |
| **Images (Pillow)** | ❌ | aucun import `PIL` dans `app/` |
| **Mémoire (§17)** | ❌ | aucun `memory_lookup` |
| **Délégation (§30) E2E** | 🟡 | décision seule, pas de transport |
| **Artifacts .xlsx/.csv/.pdf** | ❌ | `app/artifacts/generators/` vide |
| PDF avancé (pdfplumber tables) | ✅ | `app/connectors/files/pdf_connector.py:51` |
| OpenTelemetry export | 🟡 | backend `noop` si SDK absent |

---

## 2. Stubs et placeholders restants

### 2.1 Répertoires `app/` sans aucun module Python (19)

```
app/artifacts/                       app/artifacts/generators/
app/artifacts/packager/              app/artifacts/delivery/
app/connectors/images/               app/connectors/resilience/
app/governance/budget/               app/governance/versioning/
app/knowledge/embedding/             app/knowledge/enrichment/
app/knowledge/normalization/         app/messaging/handlers/
app/quality/suspicion/               app/security/certificates/
app/security/vault/                  app/storage/cache/
app/tools/database/                  app/tools/files/
app/tools/governance_tools/          app/tools/images/
app/tools/knowledge/                 app/tools/storage_tools/
```

Chacun est **documenté dans `ARCHITECTURE.md`** avec un contenu prévu qui n'existe pas.

### 2.2 Fichiers de test vides (87 sur 201)

| Dossier | Fichiers vides |
|---|---|
| `tests/agentic/` | 15 (dont les 10 scénarios §33.3) |
| `tests/factories/` | 12 |
| `tests/performance/` | 3 + `__init__` |
| `tests/security/` | 3 + `__init__` |
| `tests/integration/` | 14 (dont `test_pgvector`, `test_migrations`, `test_redis_cache`, `test_circuit_breaker`, `test_hybrid_search`, `test_repositories`, `test_object_storage`) |
| `tests/unit/` | 37 (dont `test_config`, `test_budget_enforcer`, `test_gdpr_handler`, `test_soft_delete`, `test_versioning`, `test_memory_checker`, `test_dependency_resolver`, `test_termination_evaluator`) |
| `tests/` (racine) | `conftest.py`, `containers.py` |
| `tests/api/` | `test_information_packages.py` |

### 2.3 Stubs déclarés dans le code

| Emplacement | Texte | Impact |
|---|---|---|
| `app/connectors/files/excel_connector.py:16` | `"""Excel file connector (stub - openpyxl integration in future)."""` | `.xlsx` non lu |
| `app/api/v1/requests/progress_handler.py:31` | « the handler derives a synthetic snapshot » | §41.1 non réel |
| `app/api/v1/system/metrics_router.py:50` | `except (ImportError, AttributeError, Exception): pass` | masque les erreurs métriques |
| `app/api/v1/requests/pipeline_runner.py:149-152` | `except ImportError: pass` / `except Exception: pass` | dégradation silencieuse LLM |

---

## 3. Modules `app/` non importés par le pipeline E2E

Le pipeline réel est `app/api/v1/requests/pipeline_runner.py` (700 LOC). Ses imports
effectifs couvrent : understanding, planning, LLM tasks, extractors, quality, confidence.

**Jamais importés par le pipeline** (présents mais orphelins) :

| Module | Raison |
|---|---|
| `app/knowledge/extraction/fact_extractor.py` | non branché |
| `app/provenance/lineage_tracker.py` | non branché |
| `app/governance/audit/audit_writer.py` | non branché |
| `app/governance/retention/retention_enforcer.py` | non branché |
| `app/security/pii/*` | non branché |
| `app/security/authz/*` | non branché |
| `app/registry/agent_registry.py` | non branché (pas de délégation) |
| `app/messaging/amqp/*` | non branché (broker non utilisé par le pipeline) |
| `app/storage/search/*` | non branché |
| `app/storage/object_storage/*` | non branché |
| `app/llm/tracing/llm_trace_writer.py` | non branché |
| `app/quality/checks/*` (10 modules) | appelées via `quality_scorer` seulement |
| `app/agents/pipeline/*` | doublon du runner API |
| `app/tools/registry.py` | jamais peuplé |

---

## 4. §21 — Outils internes : 2 / 35 implémentés

Vérification AST sur les 35 signatures de §21 (`def <nom>` ou `async def <nom>`) :

| Outil | Statut | Module existant à réexporter |
|---|---|---|
| `web_search` | ✅ | `app/tools/web/web_search.py` |
| `check_permission` | ✅ | `app/security/authz/permission_checker.py` |
| `open_url`, `follow_link` | ❌ | à créer |
| `postgres_query` | ❌ | à créer |
| `read_csv`, `read_excel`, `read_json`, `read_xml`, `read_pdf` | ❌ | connecteurs existants |
| `inspect_schema`, `profile_dataset` | ❌ | à créer |
| `extract_document`, `extract_image_content`, `locate_fragment` | ❌ | à créer |
| `detect_duplicates`, `validate_schema` | ❌ | à créer |
| `check_missing_values`, `check_consistency`, `check_freshness` | ❌ | à créer |
| `compare_sources` | ❌ | à créer |
| `store_source`, `store_information`, `store_evidence` | ❌ | à créer |
| `vector_search`, `hybrid_search`, `retrieve_context` | ❌ | à créer |
| `discover_agents`, `query_agent_capabilities` | ❌ | à créer |
| `send_agent_request`, `receive_agent_result` | ❌ | à créer |
| `classify_sensitivity` | ❌ | à créer |
| `create_version`, `archive_record` | ❌ | à créer |
| `write_audit_event` | ❌ | à créer |

**Conclusion : 33 outils manquants.** Le `ToolRegistry` existe (`app/tools/registry.py`)
mais n'est alimenté par aucun outil.

---

## 5. §33.3 — Scénarios agentiques : 0 / 10 couverts

| # | Scénario SPEC | Test prévu | Taille | Couvert |
|---|---|---|---|---|
| 1 | source fiable unique | `tests/agentic/test_single_reliable_source.py` | **0 o** | ❌ |
| 2 | sources contradictoires | `tests/agentic/test_conflicting_sources.py` | **0 o** | ❌ |
| 3 | information obsolète | `tests/agentic/test_stale_information.py` | **0 o** | ❌ |
| 4 | information insuffisante | `tests/agentic/test_insufficient_evidence.py` | **0 o** | ❌ |
| 5 | outil indisponible | `tests/agentic/test_tool_unavailable.py` | **0 o** | ❌ |
| 6 | agent externe indisponible | `tests/agentic/test_agent_unavailable.py` | **0 o** | ❌ |
| 7 | permission refusée | `tests/agentic/test_access_denied.py` | **0 o** | ❌ |
| 8 | demande ambiguë | `tests/agentic/test_ambiguous_request.py` | **0 o** | ❌ |
| 9 | réutilisation de mémoire | `tests/agentic/test_memory_reuse.py` | **0 o** | ❌ |
| 10 | données modifiées entre 2 recherches | `tests/agentic/test_data_changed_between_searches.py` | **0 o** | ❌ |

Couverture §33.4 (non-hallucination) : partielle — `tests/agentic/test_non_hallucination.py` vide,
mais `tests/integration/test_phase_10_e2e.py:194-247` couvre 2 cas (§0.2 findings sourcés,
hypothèses sans preuve).

---

## 6. §34 — Métriques : 14 noms présents, 0 instrumentées

`app/observability/metrics.py` déclare les 14 noms de §34 et `/v1/metrics` les expose.
Mais **aucun appelant** n'alimente le registre.

Le test `tests/api/test_evidence_conflicts.py:135` vérifie seulement la *forme* du payload,
pas l'alimentation.

| Métrique | Alimentée par |
|---|---|
| `request_success_rate` | ❌ |
| `request_latency` | ❌ |
| `source_failure_rate` | ❌ |
| `tool_failure_rate` | ❌ |
| `agent_success_rate` | ❌ |
| `confidence_distribution` | ❌ |
| `conflict_rate` | ❌ |
| `stale_data_rate` | ❌ |
| `cache_hit_rate` | ❌ |
| `vector_search_latency` | ❌ |
| `postgres_latency` | ❌ |
| `broker_latency` | ❌ |
| `llm_cost` | ❌ |
| `llm_latency` | ❌ |

---

## 7. Tests qui mockent des composants essentiels

| Catégorie | Fichiers | Composant mocké | Risque |
|---|---|---|---|
| LLM | `tests/unit/llm/test_tasks.py`, `test_model_router.py` | `httpx.MockTransport` | §22 non validé en réel |
| Web | `tests/unit/connectors/test_rss_connector.py`, `test_rest_connector.py` | `httpx.MockTransport` | §10 non validé en réel |
| DB | `tests/unit/observability/test_health_aggregator.py` (`_FakeEngine`) | SQLAlchemy | §16/§27 non validés |
| DB | `tests/unit/provenance/test_lineage_tracker.py` (`FakeConnection`) | SQLAlchemy | §12 non validé |
| DB | `tests/unit/storage/*` | SQLAlchemy / aioboto3 | §16/§27 non validés |
| Aucun conteneur réel | `tests/containers.py` (**0 o**) | — | testcontainers présent mais inutilisé |

**Docker est disponible** (29.7.2) et `testcontainers` est installé : les tests E2E réels
sont techniquement possibles dès maintenant.

---

## 8. §27 — Tables obligatoires : 20 / 28

| Table SPEC | Migration |
|---|---|
| `agents` | ✅ `0002` |
| `agent_capabilities` | ❌ |
| `agent_health` | ❌ |
| `agent_learning_profiles` | ❌ |
| `requests` | ❌ |
| `plans` | ❌ |
| `plan_steps` | ❌ |
| `executions` | ❌ |
| `iterations` | ❌ |
| `sources` | ✅ `0002` |
| `source_versions` | ❌ |
| `documents` | ✅ `0002` |
| `datasets` | ❌ |
| `information_units` | ✅ `0002` |
| `information_versions` | ❌ |
| `evidence` | ❌ |
| `claims` | ✅ `0005` |
| `conflicts` | ✅ `0005` |
| `transformations` | ✅ `0004` |
| `embeddings` | ✅ `0003` (HNSW) |
| `agent_messages` | ✅ `0005` |
| `audit_events` | ✅ `0002` |
| `access_policies` | ✅ `0005` |
| `security_classifications` | ✅ `0005` |
| `artifacts` | ✅ `0005` |
| `artifact_versions` | ✅ `0005` |
| `artifact_lineage` | ✅ `0005` |
| `artifact_delivery_events` | ❌ |

Tables supplémentaires v1 : `execution_checkpoints`, `budget_usage`, `progress`, `accounts`, `sessions`.

---

## 9. Plan de remédiation v2.0.0

| Lot | Contenu | Sections | Effort |
|---|---|---|---|
| B1 | Outils internes §21 (33 outils) + `ToolRegistry` peuplé | §21 | L |
| B2 | §41.1 → §41.3 (lifecycle, quotas, i18n) | §41.1-3 | M |
| B3 | §41.4 → §41.6 (vault, cache, chunked) | §41.4-6 | M |
| B4 | §41.7 → §41.9 (désinfo, circuit breaker, GDPR) | §41.7-9 | M |
| B5 | §41.10 → §41.12 (délégation, protocole, LLM trace) | §41.10-12 | M |
| B6 | §41.13 → §41.15 (charge, déploiement, doc) | §41.13-15 | M |
| B7 | Mémoire §17 + délégation E2E §30 + artifacts §1.1 | §17, §30, §1.1 | M |
| B8 | Migrations §27 manquantes (13 tables) | §27 | M |
| B9 | Instrumentation §34 (14 métriques câblées) | §34 | M |
| B10 | 10 scénarios §33.3 + tests sécurité §33 | §33 | M |
| B11 | E2E testcontainers (PostgreSQL+pgvector, Redis, MinIO) | §16, §33 | M |
| B12 | Documentation finale + bump 2.0.0 | toutes | S |

---

## 10. Décisions en attente

| # | Décision | Choix par défaut | Motif |
|---|---|---|---|
| D1 | Docker requis pour la suite ? | Tests conteneurs **skip** si Docker absent | CI portable |
| D2 | Nouvelle dépendance pour le vault ? | **Aucune** — AES via stdlib si indisponible, refus explicite sinon | règle « pas de dépendance sans justification » |
| D3 | Format des métriques §34 | JSON conservé, endpoint `/v1/metrics` inchangé | pas de régression |
| D4 | Version protocole §41.11 | Négociation `1.0` / `1.x` avec tolérance, refus du `2.0` | §41.11 exige la tolérance |
| D5 | Redis réel ou interface ? | `Protocol` + backend in-memory par défaut, Redis si `REDIS_URL` | évite une dépendance dure |
| D6 | Images Pillow §1.1 | Dépendance optionnelle, skip si absente | pas de dépendance dure |
