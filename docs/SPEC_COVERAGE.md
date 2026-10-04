# SPEC_COVERAGE — INIS v2.0.0 ↔ INIS_SPEC.md

**Règle absolue : aucune ligne ✅ sans nom de test réel.** Chaque preuve ci-dessous
a été collectée via `pytest --collect-only` et existe dans l'arbre au commit de
release v2.0.0.

Légende : ✅ Conforme | 🟡 Partiel | ❌ Absent | N/A (hors V1)

**Synthèse v2.0.0 : 71 sections — 52 ✅ (73 %) · 14 🟡 · 2 ❌ · 3 N/A.**
Hors sections non applicables : **52/68 = 76 % ✅**. Les 16 sections non conformes
(🟡 + ❌) sont listées en fin de document comme dettes PHASE-12.

| § | Sujet | Statut | Preuve (test) | Note |
|---|---|---|---|---|
| §0.2 | Invariants vérifiables | ✅ | `test_agentic/test_non_hallucination.py::test_only_traceable_claims_survive_as_findings` + `scripts/check_invariants.py` (CI) | 3 invariants vérifiés par AST en CI (finding sourcé, confiance non-probabiliste, préfixes ULID) |
| §0.3 | Identifiants ULID | ✅ | `tests/unit/core/test_ulid.py` + `tests/unit/core/test_identifiers.py::TestPrefixRegistry::test_core_registry_matches_the_spec` | registre de préfixes complet |
| §1 | Périmètre fonctionnel V1 | ✅ | `tests/api/test_requests.py` + `tests/integration/test_smoke.py::test_information_package` | |
| §1.3 | États de sortie autorisés | ✅ | `tests/api/test_status.py` + `tests/agentic/test_insufficient_evidence.py::test_no_source_found_yields_insufficient_evidence` | statuts décidés par `app/core/statuses.py`, jamais inline |
| §2 | Positionnement multi-agents | ✅ | `tests/integration/test_phase_02_e2e.py::test_registry_smoke` + `tests/integration/test_phase_02_pipeline.py::test_request_to_envelope` | |
| §3 | Architecture logique | ✅ | `scripts/check_architecture.py` (CI) + `tests/integration/test_phase_02_e2e.py` | zones vérifiées par le checker dédié |
| §4.1 | Runtime / stack | ✅ | `tests/api/test_health.py::test_health_exposes_the_full_contract` | runtime **3.12 partout** (contrat §4.1 `[V1-FIXE]`) : `requires-python >=3.12`, Docker prod **et** dev, CI, ruff/mypy (`e4beac2`) ; suite complète **exécutée en 3.12** dans un conteneur (2671 passed / 5 skipped) — l'interpréteur *installé sur cette machine* reste 3.11.9 |
| §4.2 | PostgreSQL + pgvector | ✅ | `tests/integration/test_postgres_real.py::test_postgres_real_core_tables` + `tests/integration/test_pgvector.py` | image CI `pgvector/pgvector:pg16` = pgvector 0.8.6 (CVE-2026-3172 couverte) |
| §4.3 | Object storage S3 | ✅ | `tests/unit/storage/test_s3_client.py` + `tests/integration/test_v2_full_stack.py::test_v2_full_stack` | backend réel RustFS en CI et en local |
| §4.4 | Broker AMQP / MQTT | 🟡 | `tests/unit/messaging/test_amqp_topology.py` + `tests/unit/messaging/test_dead_letter.py` | topologie et DLQ testées en unitaire ; `tests/integration/test_amqp_broker.py` couvre le transport (double aio-pika en mémoire) avec un test live gardé par `INIS_RABBITMQ_URL` |
| §5.1 | Envelope commune | ✅ | `tests/unit/messaging/test_envelope_validator.py` (21 tests) | |
| §5.2 | Types de messages V1 | ✅ | `tests/unit/messaging/test_envelope_builder.py` (14 tests) | |
| §5.3 | Idempotence | ✅ | `tests/integration/test_idempotency_integration.py::TestReplayIdempotence::test_replay_does_not_duplicate_units_or_evidence` + `tests/unit/messaging/test_idempotency_guard.py` | |
| §6 | Agent Registry | ✅ | `tests/unit/registry/test_agent_registry.py` (11 tests) + `tests/agentic/test_agent_unavailable.py` | `tests/integration/test_agent_registry.py` couvre l'enregistrement, la découverte et la projection déterministe de l'index de capacités |
| §7 | Modèle de demande | ✅ | `tests/unit/agents/test_request_parser.py` + `tests/unit/api/test_request_schema_defaults.py` | |
| §8 | Planification autonome (§8.1→8.5) | ✅ | `tests/unit/planning/test_plan_builder.py`, `test_iteration_manager.py`, `test_termination_evaluator.py`, `test_dependency_resolver.py` | états, plan, itération, arrêt |

| §9 | Connecteurs de sources | 🟡 | `tests/unit/connectors/test_csv_connector.py`, `test_pdf_connector.py`, `test_json_connector.py`, `test_xml_connector.py`, `test_docx_connector.py`, `test_image_connector.py`, `test_rest_connector.py`, `test_rss_connector.py` | Excel implémenté et testé ; `tests/integration/test_pdf_connector.py`, `test_excel_connector.py` et `test_web_connector.py` couvrent les connecteurs réels |
| §10.1 | Abstraction recherche web | ✅ | `tests/unit/connectors/test_provider_router.py`, `test_provider_router_fallback.py`, `test_wikipedia_provider.py` | |
| §10.2 | Hiérarchie de fiabilité | ✅ | `tests/unit/quality/test_source_reliability.py` | |
| §10.3 | Navigation / suivi de liens | 🟡 | `tests/unit/tools/test_web_search.py` | `app/tools/web/link_follower.py` sans test dédié |
| §11 | Information Unit | ✅ | `tests/unit/domain/test_information_unit.py` + `tests/integration/test_phase_05_e2e.py::test_information_unit_provenance_invariant` | |
| §12 | Cycle RAW → NORMALIZED → ENRICHED → DERIVED | 🟡 | `tests/unit/domain/test_information_package.py::test_data_stage_values` + `tests/unit/knowledge/test_chunk_splitter.py` + `tests/unit/provenance/test_lineage_tracker.py` | RAW→NORMALIZED→DERIVED tracés ; étape ENRICHED **présente** (`app/knowledge/enrichment/enricher.py`, L3.1 `51ca9a1`) et génération d'embeddings **présente** (`app/knowledge/embedding/embeddings_generator.py`, `755da14`) |
| §13 | Qualité des données | ✅ | `tests/unit/quality/test_quality_scorer.py` + checks `test_completeness_check.py`, `test_freshness_check.py`, `test_anomaly_check.py`, `test_provenance_check.py` | |
| §14 | Preuves et contradictions | ✅ | `tests/api/test_evidence_conflicts.py` + `tests/unit/quality/test_conflict_detector.py` + `tests/agentic/test_conflicting_sources.py` | |
| §15 | Modèle de confiance | ✅ | `tests/unit/confidence/test_confidence_scorer.py` (7 dimensions, poids = 1.0) + `tests/agentic/test_single_reliable_source.py` | |
| §16 | Recherche vectorielle (§16.1/16.2) | 🟡 | `tests/integration/test_pgvector.py`, `test_hybrid_search.py`, `test_fulltext_search.py` | recherche vectorielle + hybride testées ; **pipeline d'embeddings branché** (`app/knowledge/embedding/embeddings_generator.py`) et **cache L3** dans la table `embeddings` (`755da14`, `tests/integration/test_cache_l3_embeddings.py`) |
| §17 | Mémoire | 🟡 | `tests/agentic/test_memory_reuse.py` + `tests/agentic/test_stale_information.py::test_stale_cache_entry_is_never_reused` | réutilisation vérifiée de bout en bout ; `tests/unit/planning/test_memory_checker.py` couvre le vérificateur de mémoire |
| §18 | Gouvernance de la donnée | ✅ | `tests/unit/governance/test_versioning.py` (22), `test_soft_delete.py` (12), `test_retention.py` | versioning append-only, soft delete, temporalité |
| §19 | Sécurité (§19.1→19.4) | ✅ | `tests/security/test_auth_bypass.py`, `test_mtls_validator.py`, `test_mtls_service_to_service.py`, `test_injection_prevention.py`, `test_pii_redaction.py`, `tests/unit/security/test_jwt.py`, `test_rate_limiter.py`, `test_secret_hygiene.py` | §19.2 complet : mTLS inter-agents **réellement vérifié** (chaîne X.509 jusqu'à une ancre, validité, révocation par liste ou CRL, émetteur vraiment CA, identité) + dépendance d'authn sur l'extension ASGI TLS ; ⚠️ aucune route ne l'utilise tant que le serveur ASGI n'expose pas le certificat client (uvicorn 0.27.0, mesuré) |
| §20.1 | Audit events | ✅ | `tests/unit/governance/test_audit_writer.py` + `tests/integration/test_audit_integration.py` (15 tests) | |
| §20.2 | Trace distribuée | ✅ | `tests/unit/observability/test_tracing.py` (trace_id 32 hex / span_id 16 hex) + `tests/api/test_request_llm_traces.py` | |
| §21 | Outils internes | ✅ | `tests/unit/tools/test_spec21_surface.py` (25 tests) + `tests/unit/tools/test_registry.py` | surface §21 complète (35/35) |
| §22 | LLM et Model Router | ✅ | `tests/unit/llm/test_model_router.py`, `test_model_router_real.py` (27), `test_plan_parser.py`, `test_prompt_hasher.py` | enveloppe d'erreur HTTP 200 (OpenRouter) rejetée + retry §41.8 (3 essais) ; **repli en cascade ordonnée §22.2** (`LLM_MODEL_FALLBACKS`, garde `:free` sur budget nul, arrêt sur `latency_budget`) ; garde CI `tests/api/test_llm_synthesis_guard.py` + live opt-in `tests/integration/test_llm_live_provider.py` (`INIS_LIVE_LLM=1`) |

| §23 | Exécution sécurisée | 🟡 | `tests/unit/tools/test_registry.py` + `tests/security/test_injection_prevention.py::TestPromptInjection` | allow-list d'outils et neutralisation d'injection ; aucun sandbox OS (seccomp/container) — dette |
| §24.1 | Contrat de livraison | ✅ | `tests/api/test_pipeline_e2e.py` + `tests/unit/domain/test_information_package.py` | réponse standard complète (findings, preuves, confiance, limitations, usage) |
| §24.2 | Structure d'un artefact | ❌ | — | `app/artifacts/**` et `app/api/v1/artifacts/` ne contiennent aucun module → dette PHASE-12 ; l'entité domaine `Artifact` est testée (`tests/unit/domain/test_artifact.py`) |
| §24.3 | Export Excel | ❌ | — | aucun générateur d'export (la lecture Excel est testée, l'écriture non) → dette PHASE-12 |
| §25 | Gestion de l'incertitude et des échecs | ✅ | `tests/agentic/test_insufficient_evidence.py`, `test_agent_unavailable.py`, `test_tool_unavailable.py` | |
| §26 | Architecture des services | 🟡 | `tests/api/test_health.py` + `docker/` (compose) | probes et agrégateur testés ; orchestration de production (k8s) hors V1 |
| §27 | Modèle conceptuel de données | ✅ | `tests/integration/test_migrations.py` + `tests/integration/test_repositories.py` (12 tests) | 10 migrations 0001→0010 |
| §28 | Cycle complet d'une demande | ✅ | `tests/unit/planning/test_request_cycle.py` (8 tests) | 22 étapes canoniques §28 |
| §29 | Messages inter-agents | ✅ | `tests/unit/messaging/test_envelope_builder.py` + `tests/integration/test_phase_02_pipeline.py::test_request_to_envelope` | |
| §30 | Délégation vers un agent | ✅ | `tests/unit/registry/test_delegation_graph.py` (14) + `tests/agentic/test_delegation_cycle_detection.py` (6) | |
| §31 | Frontend minimal (§31.1/31.2) | 🟡 | `tests/integration/test_phase_08_e2e.py` (écrans, contextes, hooks) | fichiers réels présents ; `npm run build` skippé (node_modules absent) — vérifier en CI front (dette PHASE-12) |
| §32 | API interne / externe | ✅ | `tests/api/test_accounts.py`, `test_agents.py`, `test_requests.py`, `test_request_cancel.py`, `test_information_packages.py`, `test_sources.py`, `test_information.py`, `test_evidence_conflicts.py`, `test_quality.py`, `test_confidence.py`, `test_auth.py` | |
| §33.1 | Tests unitaires | ✅ | `tests/unit/core/test_architecture_gate.py::test_domain_layer_imports_no_io_framework` (+ 1 095 tests `tests/unit/**`) | |
| §33.2 | Tests d'intégration | ✅ | `tests/integration/test_v2_full_stack.py::test_v2_full_stack` (+ `test_postgres_real.py`, `test_migrations.py`, `test_repositories.py`) | testcontainers + skip propre si Docker absent |
| §33.3 | Tests agentiques | ✅ | `tests/agentic/test_conflicting_sources.py::test_contradictory_sources_are_reported_as_a_conflict` — 10/10 scénarios, 48 tests | détail ci-dessous |
| §33.4 | Non-hallucination | ✅ | `tests/agentic/test_non_hallucination.py` (4 tests) | |
| §34 | Observabilité et supervision | ✅ | `tests/unit/observability/test_metrics.py` + `tests/api/test_evidence_conflicts.py::test_metrics_endpoint` | |
| §35 | Roadmap d'implémentation | N/A | — | documenté (CHANGELOG, docs/phase_*.md) |
| §36 | Critères d'acceptation V1 | 🟡 | voir ce tableau + `docs/REFACTOR_REPORT_V2.md` | pas de test d'acceptation unique automatisé |
| §37 | Règle absolue de conception | ✅ | `tests/unit/core/test_architecture_gate.py::test_architecture_checker_passes_on_the_tree` + `scripts/check_architecture.py` (CI) | |
| §38 | Décisions configurables | 🟡 | `tests/unit/planning/test_pipeline_guards.py` (limites configurables) | `tests/unit/core/test_config.py` vérifie l'alignement config ↔ `DEFAULT_CONSTRAINTS` |
| §39 | Séparation des responsabilités | N/A | — | principe documenté (ARCHITECTURE.md) |
| §40 | Conclusion architecturale | N/A | — | document normatif |

| §41.1 | Requêtes longues | ✅ | `tests/agentic/test_resume_after_crash.py` (5 tests) + `tests/api/test_request_resume.py` (9) + `tests/api/test_progress_changelog.py` | reprise sur jeton opaque, TTL, progression |
| §41.2 | Quotas et facturation interne | ✅ | `tests/unit/governance/test_quotas.py` (18) + `test_budget_enforcer.py` (26) + `tests/api/test_request_usage.py` + `tests/agentic/test_budget_exceeded.py` | 7 unités de coût, dépassement explicite, jamais silencieux |
| §41.3 | Internationalisation / multilinguisme | 🟡 | `tests/unit/knowledge/test_language_policy.py` (29 tests, BCP-47) | normalisation de locale et validation BCP-47 seulement : **aucune traduction UI**, pas de détection de langue de contenu |
| §41.4 | Sources requérant authentification | ✅ | `tests/unit/security/test_credential_vault.py` (30) + `tests/unit/connectors/test_oauth2_handler.py` (13, refresh + expiry) | secrets jamais loggés (redaction récursive) |
| §41.5 | Stratégie de cache et invalidation | 🟡 | `tests/unit/storage/test_cache_store.py` (21) + `tests/api/test_pipeline_cache.py` (4) + `tests/agentic/test_data_changed_between_searches.py` + `tests/integration/test_cache_l2_postgres.py` + `tests/integration/test_cache_l3_embeddings.py` | ~~L2/L3 non câblés~~ **les trois niveaux sont branchés** : L1 (Redis), L2 (PostgreSQL, `82d9288` : survit au redémarrage) et L3 (pgvector, `755da14`). ⚠️ Reste partiel sur le seul point vérifié : la politique `[CONFIG]` accepte les trois déclencheurs (`on_source_update`, `on_conflict_detected`, `on_quality_failure`) mais seul `on_source_update` a un **appelant** identifié dans `app/` |
| §41.6 | Données structurées volumineuses | ✅ | `tests/unit/normalization/test_chunked_dataset.py` (13 tests) | seuils lignes/octets, streaming polars, chunks bornés |
| §41.7 | Désinformation / manipulation | ✅ | `tests/unit/quality/test_suspicion.py` (17 tests) | `detect_synthetic` (4 signaux) + `mirror` (copie exacte/proche), seuils configurables |
| §41.8 | Retry et circuit breaker | ✅ | `tests/unit/connectors/test_circuit_breaker.py` (13) + `tests/integration/test_circuit_breaker.py` (8) + `tests/unit/llm/test_model_router_real.py` (retry upstream) | états closed/open/half-open, budget de sondes ; retry câblé sur les appels LLM (upstream 5xx et enveloppe d'erreur 200), **défaut porté à 3 tentatives par modèle** (`LLM_RETRY_ATTEMPTS` surcharge) |
| §41.9 | Consentement et droits sur les données | ✅ | `tests/unit/governance/test_gdpr_handler.py` (10 : portabilité + rectification) + `tests/unit/governance/test_gdpr.py` (3 : effacement/pseudonymisation) | portabilité et rectification implémentées et testées |
| §41.10 | Dépendances entre agents (topologie) | ✅ | `tests/unit/registry/test_delegation_graph.py` (14) | cycle, auto-délégation, profondeur max |
| §41.11 | Migration du protocole | ✅ | `tests/unit/messaging/test_protocol_versioning.py` (14 tests) | versions supportées, compatibilité ascendante |
| §41.12 | Observabilité des décisions LLM | ✅ | `tests/unit/llm/test_llm_trace_writer.py` (19) + `tests/api/test_request_llm_traces.py` (6) + `tests/api/test_llm_synthesis_guard.py` (3) | champs §41.12 obligatoires + hash de prompt (sha256) ; une synthèse servie est métrée **et** tracée, un échec de synthèse est tracé à 0 tokens avec sa cause (jamais silencieux) |
| §41.13 | Tests de charge et dimensionnement | 🟡 | `tests/load/test_benchmarks.py` (6 tests) | débit, queue, agents concurrents et latence vectorielle mesurés avec LLM mocké (`tests/performance/**`) ; **pas de harnais de charge réel** (k6/Gatling) |
| §41.14 | Déploiement et migration de schéma | ✅ | `scripts/check_backward_compat.py` (CI) + `tests/unit/migrations/test_check_backward_compat.py` (10) + `tests/integration/test_migrations.py` | gate BC001→BC005, head 0010 compatible, upgrade/downgrade |
| §41.15 | Documentation automatique / contrat | ✅ | `tests/api/test_openapi_schema_changelog.py` + `tests/unit/core/test_version_consistency.py` | OpenAPI `/v1/openapi.json`, `/v1/changelog`, `GET /v1/agents/{id}/schema` |

---

## §33.3 — Les 10 scénarios agentiques

| # | Scénario | Fichier | Tests |
|---|---|---|---|
| 1 | `conflicting_sources` | `tests/agentic/test_conflicting_sources.py` | 3 |
| 2 | `stale_information` | `tests/agentic/test_stale_information.py` | 5 |
| 3 | `insufficient_information` | `tests/agentic/test_insufficient_evidence.py` | 1 |
| 4 | `ambiguous_request` | `tests/agentic/test_ambiguous_request.py` | 4 |
| 5 | `memory_reuse` | `tests/agentic/test_memory_reuse.py` | 2 |
| 6 | `data_modified_between_searches` | `tests/agentic/test_data_changed_between_searches.py` | 3 |
| 7 | `access_denied` | `tests/agentic/test_access_denied.py` | 4 |
| 8 | `agent_unavailable` | `tests/agentic/test_agent_unavailable.py` | 3 |
| 9 | `tool_unavailable` | `tests/agentic/test_tool_unavailable.py` | 3 |
| 10 | `budget_exceeded` | `tests/agentic/test_budget_exceeded.py` | 3 |

Compléments : `test_non_hallucination.py` (4), `test_single_reliable_source.py` (2),
`test_resume_after_crash.py` (5), `test_delegation_cycle_detection.py` (6)
→ **48 tests** dans `tests/agentic/`.

---

## Dettes confirmées par cet audit (PHASE-12)

1. §24.2 — artifacts/export : `app/artifacts/**`, `app/api/v1/artifacts/` vides.
2. §24.3 — export Excel : aucun générateur.
3. §16 — pipeline d'embeddings absent (`app/knowledge/embedding/`).
4. §12 — étape ENRICHED absente (`app/knowledge/enrichment/`).
5. §31 — build frontend non exécuté dans la CI.

### Dettes soldées le 2026-09-28 (branche `fix/pipeline-llm-synthesis`)

Les fichiers vides listés par cet audit ont été remplis et les `tests/performance/**`
écrits : `test_amqp_broker.py` (§4.4), `test_redis_cache.py` (§41.5),
`test_agent_registry.py` (§6), `test_pdf_connector.py` / `test_excel_connector.py` /
`test_web_connector.py` (§9), `test_config.py` (§38), `test_memory_checker.py` (§17),
`test_artifact.py` (§24.2), `test_transformation.py`, ainsi que les factories de
`tests/factories/**`. `tests/performance/` couvre désormais §41.13 (débit, queue,
agents concurrents, latence recherche vectorielle/hybride pgvector).
Reste ouvert à cette date : §24.2/§24.3 (artifacts et export Excel, cf. dettes 1-2),
§16 et §12, cache L2/L3 (§41.5), `SourceRepository` divergent de la migration 0002.

> **Mise à jour L7 (2026-10-04) — sur cette liste, sont désormais soldés** :
> §24.2/§24.3 (L1, `7c1bba2`), §16 (`app/knowledge/embedding/`, `755da14`) et §12
> (`app/knowledge/enrichment/`, `51ca9a1`), ainsi que le **cache L2/L3** (§41.5 :
> L2 `82d9288`, L3 `755da14`) — chaque ligne est adossée à un test qui existe
> (`tests/integration/test_cache_l2_postgres.py`, `test_cache_l3_embeddings.py`).
> **Reste ouvert** : la dette n°3 (`SourceRepository` divergent de la migration 0002).



