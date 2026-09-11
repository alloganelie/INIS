# INIS — Architecture définitive et complète

> Version finale. Couvre l'intégralité du projet, toutes phases confondues.
> Chaque fichier a une responsabilité unique et bornée.
> Aucune logique métier dans les couches de stockage.
> Aucune logique de stockage dans le domaine.

---

## Racine du projet

```
inis/
├── main.py                        # Point d'entrée uvicorn (hors app/)
├── pyproject.toml                 # Dépendances, outils, metadata
├── alembic.ini                    # Configuration Alembic
├── .env.example                   # Toutes les variables documentées
├── .env                           # Variables locales (non versionné)
├── .gitignore
├── .dockerignore
├── docker-compose.yml             # PostgreSQL, Redis, RabbitMQ, MinIO, MQTT, Vault, OTel, Grafana
├── docker-compose.test.yml        # Stack isolée tests
├── docker-compose.prod.yml        # Stack production
├── Makefile                       # migrate, test, lint, run, certs, benchmark
└── README.md
```

---

## app/

### app/main.py

```
app/
└── main.py                        # Instancie FastAPI, monte middlewares, routers, lifecycle
```

---

### app/core/

```
app/core/
├── __init__.py
├── config.py                      # BaseSettings Pydantic — tous les [CONFIG]
├── constants.py                   # Préfixes ID, version protocole, valeurs non configurables
├── logging.py                     # structlog + processeurs OpenTelemetry
├── errors.py                      # Hiérarchie exceptions métier INIS
├── hashing.py                     # sha256, before_hash / after_hash déterministe
└── lifecycle.py                   # Startup / shutdown : DB, broker, cache, workers
```

---

### app/domain/

#### Enums

```
app/domain/enums/
├── __init__.py
├── data_stage.py                  # raw | normalized | enriched | derived
├── epistemic_status.py            # fact | hypothesis | assumption | uncertainty
├── request_status.py              # RECEIVED → DELIVERED | FAILED | CANCELLED
├── output_status.py               # SUCCESS | PARTIAL_SUCCESS | … | CANCELLED
├── record_status.py               # active | archived | deleted | superseded
├── audit_action.py                # read | write | update | delete | transmit | search
├── audit_actor_type.py            # agent | user | system
├── audit_result.py                # success | denied | failed
├── agent_status.py                # available | degraded | unavailable | maintenance
├── conflict_severity.py           # low | medium | high
├── conflict_difference.py         # value | definition | date | methodology | scope
├── resolution_status.py           # open | investigated | unresolved | resolved
├── plan_step_status.py            # pending | running | done | failed
├── iteration_decision.py          # continue | stop | delegate | fail
├── output_format.py               # evidence_package | json | csv | xlsx | pdf | xml
├── auth_method.py                 # mtls | jwt | api_key
├── message_type.py                # 23 types du protocole
├── message_priority.py            # low | normal | high | critical
├── sensitivity_level.py           # low | medium | high | critical
├── artifact_type.py               # dataset_export | report | document | other
├── information_type.py            # text | number | table | record | image_region | document_fragment
├── source_type.py                 # web | api | database | file | agent
├── trust_level.py                 # full | partial | minimal
├── circuit_breaker_state.py       # open | closed | half_open
├── delegation_effect.py           # allow | deny
├── requirement_type.py            # web | api | database | file | memory
└── worker_status.py               # idle | running | paused | stopped
```

#### Value Objects

```
app/domain/value_objects/
├── __init__.py
├── ulid.py                        # Génération et validation ULID Crockford 26 chars
├── identifier.py                  # Constructeurs REQ_, MSG_, INF_, SRC_… validés
├── trace_context.py               # trace_id (32 hex), span_id (16 hex), correlation_id
├── date_range.py                  # DateRange avec cohérence from/to
├── confidence_score.py            # Float 0-1 avec 7 dimensions et explication
├── quality_score.py               # Float 0-1 avec pondération configurable
├── semver.py                      # Version sémantique avec comparaison
├── storage_ref.py                 # s3://bucket/path avec validation format
├── sha256_hash.py                 # Hash immuable avec vérification intégrité
├── bcp47_language.py              # Code langue BCP-47 validé
└── money.py                       # Montant + devise pour budgets et coûts
```

#### Entities

```
app/domain/entities/
├── __init__.py
│
│ — Agents et requêtes —
├── agent.py                       # AgentIdentity, AgentHealth, PerformanceProfile, LearningProfile
├── request.py                     # InformationRequest, RequestConstraints, RequiredOutput
├── requirements.py                # Requirements : exigences extraites et structurées
├── information_response.py        # InformationResponse : réponse finale complète
├── progress.py                    # Progress : état et avancement d'une exécution
├── agent_delegation.py            # AgentDelegationRequest, AgentDelegationResponse
│
│ — Plan et exécution —
├── plan.py                        # Plan, PlanStep
├── iteration.py                   # Iteration
├── budget.py                      # Budget, BudgetDimension, UsageReport
│
│ — Sources et données —
├── query.py                       # Query passé à connector.discover()
├── source_candidate.py            # SourceCandidate retourné par connector.discover()
├── raw_source.py                  # RawSource retourné par connector.retrieve()
├── source.py                      # Source, SourceVersion, SourceMetadata, SourceSuspicion
├── document.py                    # Document
├── dataset.py                     # Dataset, DataChunk
├── schema.py                      # Schema retourné par inspect_schema()
├── dataset_profile.py             # DatasetProfile retourné par profile_dataset()
├── validation_result.py           # ValidationResult retourné par validate_schema()
├── duplicate.py                   # Duplicate retourné par detect_duplicates()
├── chunk_result.py                # ChunkResult retourné par process_chunk()
│
│ — Connectors et outils —
├── search_result.py               # SearchResult retourné par web_search()
├── health_status.py               # HealthStatus retourné par connector.health_check()
├── connector_metadata.py          # ConnectorMetadata retourné par connector.metadata()
│
│ — LLM —
├── llm_task.py                    # LLMTask passé au ModelRouter
├── llm_response.py                # LLMResponse retourné par ModelRouter
│
│ — Knowledge —
├── information_unit.py            # InformationUnit, InformationVersion
├── evidence.py                    # Evidence
├── claim.py                       # Claim
├── conflict.py                    # Conflict
├── transformation.py              # Transformation
├── memory_result.py               # MemoryResult, MemoryCandidate
├── quality_result.py              # QualityResult retourné par quality checks
│
│ — Gouvernance —
├── artifact.py                    # Artifact, ArtifactVersion, ArtifactLineage
├── audit_event.py                 # AuditEvent
├── llm_decision_trace.py          # LLMDecisionTrace
├── access_policy.py               # AccessPolicy
├── classification.py              # SecurityClassification, PIIClassification
├── retention_policy.py            # RetentionPolicy par type de ressource
│
│ — Protocole —
├── envelope.py                    # Envelope, EnvelopeSender, EnvelopeRecipient, EnvelopeSecurity
├── embedding.py                   # Embedding
└── credential.py                  # CredentialRef — pointeur vault, jamais de valeur
```

#### Interfaces (Protocols)

```
app/domain/interfaces/
├── __init__.py
├── versionable.py                 # create_version, get_version, list_versions
├── auditable.py                   # write_audit_event
├── soft_deletable.py              # archive, delete logique
├── provenanceable.py              # assert_provenance_complete
├── source_connector.py            # discover, retrieve, inspect, health_check, metadata
├── search_provider.py             # search(query, limit) → list[SearchResult]
├── message_broker.py              # publish, subscribe
├── model_router.py                # complete(task, prompt) → LLMResponse
└── chunked_processor.py           # stream, process_chunk, merge_results
```

---

### app/agents/

```
app/agents/
├── __init__.py
│
├── runtime/
│   ├── __init__.py
│   ├── agent_runner.py            # Boucle principale : reçoit → comprend → planifie → exécute
│   ├── state_machine.py           # Machine d'états RECEIVED → DELIVERED
│   ├── budget_tracker.py          # Suivi tokens, requêtes, temps, coût en temps réel
│   ├── progress_tracker.py        # Persiste l'avancement étape par étape
│   └── resume_manager.py          # resume_token, last_committed_step, reprise sur crash
│
├── understanding/
│   ├── __init__.py
│   ├── request_parser.py          # Parse et valide l'InformationRequest entrant
│   ├── requirement_extractor.py   # LLM → Requirements structurées
│   ├── clarification_detector.py  # Détecte si la demande est trop ambiguë
│   └── context_enricher.py        # Enrichit le contexte avec métadonnées de session
│
├── decision/
│   ├── __init__.py
│   ├── termination_evaluator.py   # Évalue les 6 critères d'arrêt
│   ├── delegation_decider.py      # Décide si déléguer et à quel agent
│   └── partial_result_packager.py # Construit un résultat partiel si arrêt anticipé
│
└── pipeline/
    ├── __init__.py
    ├── pipeline_coordinator.py    # Orchestre les 28 étapes du cycle complet
    └── step_executor.py           # Exécute un step individuel avec timeout et retry
```

---

### app/planning/

```
app/planning/
├── __init__.py
├── plan_builder.py                # build_plan() depuis les Requirements
├── plan_executor.py               # Exécute les steps, respecte depends_on
├── dependency_resolver.py         # Résout l'ordre d'exécution depuis le graphe de dépendances
├── step_selector.py               # Choisit quel outil pour chaque type d'exigence
├── iteration_manager.py           # Gère les itérations, hypothèses, décisions
├── memory_checker.py              # memory_lookup() : hybride search + fraîcheur + politique
└── source_discoverer.py           # Découverte des sources pertinentes pour un plan
```

---

### app/tools/

```
app/tools/
├── __init__.py
├── registry.py                    # Registre des outils disponibles + sélection dynamique
│
├── web/
│   ├── __init__.py
│   ├── web_search.py              # web_search(query, limit) → list[SearchResult]
│   ├── url_opener.py              # open_url(url) → Document
│   └── link_follower.py           # follow_link(url) → Document
│
├── database/
│   ├── __init__.py
│   └── postgres_query.py          # postgres_query(sql, params) → list[dict]
│
├── files/
│   ├── __init__.py
│   ├── csv_reader.py              # read_csv(path) → Dataset
│   ├── excel_reader.py            # read_excel(path) → Dataset
│   ├── json_reader.py             # read_json(path) → Dataset
│   ├── xml_reader.py              # read_xml(path) → Dataset
│   ├── pdf_reader.py              # read_pdf(path) → Document
│   └── document_reader.py         # extract_document(path) → Document
│
├── images/
│   ├── __init__.py
│   └── image_analyzer.py          # extract_image_content(path) → list[InformationUnit]
│
├── knowledge/
│   ├── __init__.py
│   ├── fragment_locator.py        # locate_fragment(document_id, query)
│   ├── vector_searcher.py         # vector_search(query_vector, limit)
│   └── hybrid_searcher.py         # hybrid_search(query, filters)
│
├── storage_tools/
│   ├── __init__.py
│   ├── source_storer.py           # store_source(source) → source_id
│   ├── information_storer.py      # store_information(unit) → information_id
│   └── evidence_storer.py         # store_evidence(evidence) → evidence_id
│
└── governance_tools/
    ├── __init__.py
    ├── version_tool.py            # create_version(resource_id, change)
    ├── archive_tool.py            # archive_record(resource_id)
    └── audit_tool.py              # write_audit_event(event)
```

---

### app/connectors/

```
app/connectors/
├── __init__.py
├── base.py                        # BaseConnector : lifecycle, logging, health
│
├── resilience/
│   ├── __init__.py
│   ├── circuit_breaker.py         # États open/closed/half_open par connecteur
│   ├── retry_policy.py            # Backoff exponentiel configurable
│   └── resilience_state.py        # Persiste l'état des circuit breakers (Redis)
│
├── web/
│   ├── __init__.py
│   ├── provider_router.py         # Route vers le bon fournisseur selon config
│   ├── providers/
│   │   ├── __init__.py
│   │   ├── brave_provider.py
│   │   ├── serper_provider.py
│   │   └── mock_provider.py       # Tests uniquement
│   └── extractors/
│       ├── __init__.py
│       ├── trafilatura_extractor.py
│       └── readability_extractor.py
│
├── api/
│   ├── __init__.py
│   ├── rest_connector.py          # Appels REST génériques
│   └── auth/
│       ├── __init__.py
│       ├── oauth2_handler.py
│       ├── api_key_handler.py
│       └── basic_auth_handler.py
│
├── database/
│   ├── __init__.py
│   └── postgres_connector.py      # Source PostgreSQL externe
│
├── files/
│   ├── __init__.py
│   ├── csv_connector.py
│   ├── excel_connector.py
│   ├── json_connector.py
│   ├── xml_connector.py
│   ├── pdf_connector.py
│   └── docx_connector.py
│
└── images/
    ├── __init__.py
    └── image_connector.py
```

---

### app/knowledge/

```
app/knowledge/
├── __init__.py
│
├── extraction/
│   ├── __init__.py
│   ├── text_extractor.py          # Texte → list[InformationUnit]
│   ├── table_extractor.py         # Tableau → InformationUnit type=table
│   ├── number_extractor.py        # Valeurs numériques + unité + contexte
│   └── fragment_extractor.py      # Fragments document avec position exacte
│
├── normalization/
│   ├── __init__.py
│   ├── date_normalizer.py         # Harmonisation formats de date → ISO 8601
│   ├── number_normalizer.py       # Normalisation unités et formats numériques
│   ├── language_normalizer.py     # Détection langue + politique de traduction
│   ├── translation_service.py     # Appel modèle de traduction + trace TRF_
│   ├── locale_normalizer.py       # Formats selon région (virgule, devises, dates)
│   └── deduplicator.py            # Détection et fusion de doublons
│
├── enrichment/
│   ├── __init__.py
│   ├── metadata_enricher.py       # Ajout métadonnées source, fraîcheur, fiabilité
│   └── classification_enricher.py # Classification sensibilité PII
│
├── chunking/
│   ├── __init__.py
│   ├── chunk_splitter.py          # Découpe un Dataset volumineux en DataChunk
│   ├── chunk_processor.py         # Traite un DataChunk → ChunkResult
│   └── chunk_merger.py            # Fusionne list[ChunkResult] → Dataset
│
└── embedding/
    ├── __init__.py
    ├── embedding_generator.py     # Génère vecteurs via modèle configurable
    └── embedding_indexer.py       # Indexe dans pgvector
```

---

### app/quality/

```
app/quality/
├── __init__.py
│
├── checks/
│   ├── __init__.py
│   ├── completeness_check.py
│   ├── validity_check.py
│   ├── consistency_check.py
│   ├── uniqueness_check.py
│   ├── type_conformity_check.py
│   ├── freshness_check.py
│   ├── provenance_check.py
│   ├── anomaly_check.py
│   ├── temporal_consistency_check.py
│   └── cross_source_consistency_check.py
│
├── score/
│   ├── __init__.py
│   ├── quality_scorer.py          # Calcul quality_score pondéré configurable
│   └── quality_reporter.py        # Rapport structuré des contrôles
│
├── conflict/
│   ├── __init__.py
│   ├── conflict_detector.py       # detect_conflicts(units) → list[Conflict]
│   ├── conflict_classifier.py     # classify_difference(a, b) → difference_type
│   ├── severity_assessor.py       # assess_severity(a, b) → severity
│   └── conflict_resolver.py       # Tentatives de résolution automatique
│
└── suspicion/
    ├── __init__.py
    ├── synthetic_detector.py      # Détecte contenu généré par IA
    ├── mirror_detector.py         # Détecte sites miroirs ou copies
    └── bias_assessor.py           # Évalue le biais éditorial systématique d'une source
```

---

### app/confidence/

```
app/confidence/
├── __init__.py
│
├── dimensions/
│   ├── __init__.py
│   ├── source_reliability.py
│   ├── source_freshness.py
│   ├── extraction_confidence.py
│   ├── data_quality_signal.py
│   ├── evidence_strength.py
│   ├── cross_source_agreement.py
│   └── methodological_consistency.py
│
├── confidence_scorer.py           # Calcul confidence_score avec formule configurable
└── confidence_explainer.py        # Génère l'explication lisible du score
```

---

### app/provenance/

```
app/provenance/
├── __init__.py
├── lineage_tracker.py             # Trace source → transformation → output
├── transformation_recorder.py    # Enregistre chaque TRF_ avec inputs/outputs/justification
└── provenance_validator.py        # Vérifie provenance_complete sur une entité
```

---

### app/governance/

```
app/governance/
├── __init__.py
│
├── versioning/
│   ├── __init__.py
│   ├── version_manager.py         # create_version, get_version, list_versions, diff
│   └── hash_computer.py           # before_hash / after_hash déterministe
│
├── audit/
│   ├── __init__.py
│   ├── audit_writer.py            # write_audit_event, flush, batch
│   └── audit_query.py             # Requêtes par resource, actor, période
│
├── budget/
│   ├── __init__.py
│   ├── budget_enforcer.py         # Coupe l'exécution si budget dépassé
│   └── usage_reporter.py          # Génère le usage_report en sortie de réponse
│
├── retention/
│   ├── __init__.py
│   ├── retention_enforcer.py      # Applique les politiques de durée de vie
│   └── gdpr_handler.py            # Droit à l'oubli, rectification, portabilité
│
└── lifecycle/
    ├── __init__.py
    ├── soft_delete_manager.py     # ACTIVE → ARCHIVED → DELETED
    └── pseudonymizer.py           # Pseudonymisation actor_id sur demande RGPD
```

---

### app/security/

```
app/security/
├── __init__.py
│
├── authn/
│   ├── __init__.py
│   ├── mtls_validator.py          # Validation certificats mTLS inter-agents
│   ├── jwt_validator.py           # Validation JWT API HTTP
│   └── api_key_validator.py       # Validation API keys administration
│
├── authz/
│   ├── __init__.py
│   ├── rbac_engine.py
│   ├── abac_engine.py
│   ├── policy_evaluator.py        # Évalue AccessPolicy pour une action
│   ├── policy_loader.py           # Charge les politiques depuis DB + cache
│   └── permission_checker.py      # check_permission(agent_id, resource, action)
│
├── pii/
│   ├── __init__.py
│   ├── pii_detector.py
│   ├── sensitivity_classifier.py  # classify_sensitivity(data) → Classification
│   └── redactor.py                # Redacte les PII selon la politique
│
├── rate_limiting/
│   ├── __init__.py
│   ├── rate_limiter.py            # Limite par agent_id, IP, endpoint
│   └── rate_limit_store.py        # Compteurs Redis pour les fenêtres glissantes
│
├── certificates/
│   ├── __init__.py
│   ├── cert_loader.py             # Charge les certificats mTLS depuis le filesystem/vault
│   └── cert_validator.py          # Valide les certificats des agents entrants
│
└── vault/
    ├── __init__.py
    ├── vault_client.py            # Interface HashiCorp Vault ou équivalent
    └── credential_resolver.py     # Résout un CredentialRef → valeur effective
```

---

### app/messaging/

```
app/messaging/
├── __init__.py
│
├── amqp/
│   ├── __init__.py
│   ├── amqp_broker.py             # Implémentation MessageBroker via aio-pika
│   ├── amqp_consumer.py           # Consommation queues avec acknowledge
│   ├── amqp_publisher.py          # Publication avec confirmation
│   ├── topology.py                # Exchanges, queues, routing keys — déclarés au démarrage
│   ├── dead_letter_handler.py     # Traitement messages en dead letter queue
│   └── amqp_health.py             # Vérification connectivité RabbitMQ
│
├── mqtt/
│   ├── __init__.py
│   ├── mqtt_broker.py             # Implémentation optionnelle via gmqtt
│   └── mqtt_health.py
│
├── protocol/
│   ├── __init__.py
│   ├── envelope_builder.py        # Construit une Envelope valide
│   ├── envelope_validator.py      # Valide structure et version protocole
│   ├── idempotency_guard.py       # Unicité message_id, renvoi réponse précédente
│   └── version_negotiator.py      # Négociation version lors du register
│
└── handlers/
    ├── __init__.py
    ├── information_request_handler.py
    ├── agent_register_handler.py
    ├── agent_heartbeat_handler.py
    ├── capability_query_handler.py
    ├── delegation_request_handler.py
    ├── cancel_request_handler.py
    └── audit_event_handler.py
```

---

### app/registry/

```
app/registry/
├── __init__.py
├── agent_registry.py              # CRUD agents + découverte par capacité
├── capability_index.py            # Index inversé capacité → agents
├── heartbeat_monitor.py           # TTL monitoring, passage en unavailable
├── trust_graph.py                 # Graphe de confiance inter-agents
└── delegation_graph.py            # Détection de cycles, profondeur max
```

---

### app/llm/

```
app/llm/
├── __init__.py
│
├── router/
│   ├── __init__.py
│   ├── model_router.py            # Sélection modèle selon tâche, coût, latence, dispo
│   ├── task_classifier.py         # Classifie la nature de la tâche LLM
│   ├── fallback_chain.py          # Chaîne de fallback si modèle indisponible
│   └── cost_tracker.py            # Comptabilise tokens et coût par appel LLM
│
├── prompts/
│   ├── __init__.py
│   ├── understanding_prompt.py    # Prompt : compréhension de la demande
│   ├── planning_prompt.py         # Prompt : génération du plan
│   ├── classification_prompt.py   # Prompt : classification d'informations
│   ├── conflict_detection_prompt.py
│   └── confidence_signal_prompt.py
│
├── parsers/
│   ├── __init__.py
│   ├── plan_parser.py             # Parse la réponse LLM en Plan structuré
│   ├── requirement_parser.py      # Parse la réponse LLM en Requirements
│   └── classification_parser.py   # Parse la réponse LLM en Classification
│
├── tasks/
│   ├── __init__.py
│   ├── understanding_task.py
│   ├── planning_task.py
│   ├── classification_task.py
│   ├── conflict_detection_task.py
│   └── confidence_signal_task.py
│
└── tracing/
    ├── __init__.py
    ├── llm_trace_writer.py        # Écrit LLMDecisionTrace après chaque appel
    └── prompt_hasher.py           # sha256 du prompt sans stocker le texte en clair
```

---

### app/artifacts/

```
app/artifacts/
├── __init__.py
│
├── generators/
│   ├── __init__.py
│   ├── xlsx_generator.py          # Génère .xlsx avec onglets données/sources/provenance
│   ├── csv_generator.py           # Génère .csv avec en-têtes et métadonnées
│   ├── json_generator.py          # Génère .json structuré
│   ├── xml_generator.py           # Génère .xml avec schéma
│   └── pdf_generator.py           # Génère .pdf avec mise en page
│
├── packager/
│   ├── __init__.py
│   ├── result_packager.py         # Construit la réponse finale complète
│   └── evidence_packager.py       # Construit le package de preuves
│
└── delivery/
    ├── __init__.py
    ├── delivery_service.py        # Dépose l'artifact dans object storage + DB
    └── callback_notifier.py       # Notifie l'agent demandeur (AMQP / webhook)
```

---

### app/workers/

```
app/workers/
├── __init__.py
├── request_worker.py              # Consomme les requêtes depuis la queue AMQP
├── heartbeat_worker.py            # Envoie heartbeats périodiques au registre
├── retention_worker.py            # Applique les politiques de rétention (cron)
└── cleanup_worker.py              # Nettoyage artefacts expirés et checkpoints périmés
```

---

### app/storage/

```
app/storage/
├── __init__.py
│
├── database/
│   ├── __init__.py
│   ├── engine.py                  # Engine SQLAlchemy async, pool, lifecycle
│   ├── session.py                 # AsyncSession factory, dependency injection FastAPI
│   └── health.py                  # Vérification connectivité PostgreSQL
│
├── models/
│   ├── __init__.py
│   ├── base.py                    # DeclarativeBase, TimestampMixin, SoftDeleteMixin
│   ├── agent.py
│   ├── agent_capability.py
│   ├── agent_health.py
│   ├── agent_learning.py
│   ├── request.py
│   ├── plan.py
│   ├── plan_step.py
│   ├── execution.py
│   ├── execution_checkpoint.py    # Checkpoint pour reprise sur interruption
│   ├── iteration.py
│   ├── progress.py                # Avancement pas à pas d'une exécution
│   ├── budget_usage.py            # Consommation réelle par dimension et par requête
│   ├── source.py
│   ├── source_version.py
│   ├── document.py
│   ├── dataset.py
│   ├── information_unit.py        # + colonne tsvector pour full-text
│   ├── information_version.py
│   ├── evidence.py
│   ├── claim.py
│   ├── conflict.py
│   ├── transformation.py
│   ├── embedding.py               # + colonne vector(1536) HNSW
│   ├── agent_message.py           # + contrainte UNIQUE sur message_id
│   ├── audit_event.py
│   ├── llm_decision_trace.py
│   ├── access_policy.py
│   ├── classification.py
│   ├── artifact.py
│   ├── artifact_version.py
│   ├── artifact_lineage.py
│   └── artifact_delivery.py
│
├── repositories/
│   ├── __init__.py
│   ├── base.py                    # BaseRepository : get, list, save, soft_delete
│   ├── agent_repository.py
│   ├── request_repository.py
│   ├── plan_repository.py
│   ├── source_repository.py
│   ├── document_repository.py
│   ├── dataset_repository.py
│   ├── information_repository.py
│   ├── evidence_repository.py
│   ├── claim_repository.py
│   ├── conflict_repository.py
│   ├── transformation_repository.py
│   ├── embedding_repository.py
│   ├── audit_repository.py
│   ├── llm_trace_repository.py
│   ├── access_policy_repository.py
│   ├── artifact_repository.py
│   ├── budget_repository.py
│   └── progress_repository.py
│
├── object_storage/
│   ├── __init__.py
│   ├── s3_client.py               # Client S3/MinIO async
│   ├── object_uploader.py         # Upload + sha256 + storage_ref
│   └── object_downloader.py       # Download + vérification sha256
│
├── cache/
│   ├── __init__.py
│   ├── redis_client.py            # Connexion Redis async
│   ├── l1_cache.py                # Cache résultats Web et API (TTL court)
│   ├── cache_invalidator.py       # Invalidation sur update source / conflit / qualité
│   └── cache_health.py
│
└── search/
    ├── __init__.py
    ├── vector_search.py           # vector_search(query_vector, limit)
    ├── fulltext_search.py         # Full-text PostgreSQL tsvector
    └── hybrid_search.py           # Fusion sémantique 0.6 + lexical 0.4
```

---

### app/observability/

```
app/observability/
├── __init__.py
├── tracing.py                     # OpenTelemetry tracer, spans, propagation
├── metrics.py                     # Compteurs, histogrammes, gauges — 14 métriques spec §34
├── health_aggregator.py           # Agrège état PostgreSQL, Redis, RabbitMQ, MinIO, circuit breakers
├── health_endpoint.py             # /v1/health — résultat de health_aggregator
└── metrics_endpoint.py            # /v1/metrics — exposition format Prometheus
```

---

### app/api/

```
app/api/
├── __init__.py
├── dependencies.py                # Injection : session DB, broker, auth, trace, rate limiter
│
├── middleware/
│   ├── __init__.py
│   ├── trace_middleware.py        # Injecte trace_id et span_id dans chaque requête
│   ├── auth_middleware.py         # Valide JWT / API key avant routing
│   ├── rate_limit_middleware.py   # Applique les limites par agent_id et endpoint
│   └── request_id_middleware.py   # Génère et attache un request_id unique
│
└── v1/
    ├── __init__.py
    ├── router.py                  # Agrège tous les routers v1
    │
    ├── requests/
    │   ├── __init__.py
    │   ├── router.py              # POST /v1/requests, GET /{id}, POST /{id}/cancel
    │   ├── progress_handler.py    # GET /v1/requests/{id}/progress
    │   ├── events_handler.py      # GET /v1/requests/{id}/events — SSE temps réel
    │   ├── schemas.py
    │   └── handlers.py
    │
    ├── information/
    │   ├── __init__.py
    │   ├── router.py              # GET /v1/information/{id}
    │   └── schemas.py
    │
    ├── sources/
    │   ├── __init__.py
    │   ├── router.py              # GET /v1/sources/{id}
    │   └── schemas.py
    │
    ├── evidence/
    │   ├── __init__.py
    │   ├── router.py              # GET /v1/evidence/{id}
    │   └── schemas.py
    │
    ├── conflicts/
    │   ├── __init__.py
    │   ├── router.py              # GET /v1/conflicts/{id}
    │   └── schemas.py
    │
    ├── artifacts/
    │   ├── __init__.py
    │   ├── router.py              # GET /v1/artifacts/{id}, GET /v1/artifacts/{id}/download
    │   └── schemas.py
    │
    ├── agents/
    │   ├── __init__.py
    │   ├── router.py              # GET /v1/agents, POST /v1/agents/register, GET /{id}
    │   ├── schema_endpoint.py     # GET /v1/agents/{id}/schema
    │   └── schemas.py
    │
    └── system/
        ├── __init__.py
        ├── health_router.py       # GET /v1/health
        ├── metrics_router.py      # GET /v1/metrics
        ├── changelog_router.py    # GET /v1/changelog
        └── docs_router.py         # GET /v1/docs, /v1/openapi.json
```

---

## migrations/

```
migrations/
├── env.py                         # Configuration Alembic async
├── script.py.mako
└── versions/
    ├── 0001_create_extensions.py  # pgvector, pg_trgm, unaccent
    ├── 0002_create_agents.py
    ├── 0003_create_requests.py
    ├── 0004_create_plans.py
    ├── 0005_create_sources.py
    ├── 0006_create_documents.py
    ├── 0007_create_datasets.py
    ├── 0008_create_information_units.py
    ├── 0009_create_evidence_claims.py
    ├── 0010_create_conflicts.py
    ├── 0011_create_transformations.py
    ├── 0012_create_embeddings.py
    ├── 0013_create_agent_messages.py
    ├── 0014_create_audit_events.py
    ├── 0015_create_llm_decision_traces.py
    ├── 0016_create_access_policies.py
    ├── 0017_create_artifacts.py
    ├── 0018_create_execution_checkpoints.py
    ├── 0019_create_budget_usage.py
    ├── 0020_create_progress.py
    ├── 0021_add_tsvector_columns.py
    ├── 0022_add_gin_indexes.py
    ├── 0023_add_hnsw_index.py
    ├── 0024_add_unique_constraints.py
    └── 0025_add_provenance_constraints.py
```

---

## tests/

```
tests/
├── __init__.py
├── conftest.py                    # Fixtures globales : DB, session, broker mock, factories
├── containers.py                  # Testcontainers : PostgreSQL, Redis, RabbitMQ, MinIO
│
├── factories/
│   ├── __init__.py
│   ├── agent_factory.py
│   ├── request_factory.py
│   ├── source_factory.py
│   ├── document_factory.py
│   ├── dataset_factory.py
│   ├── information_unit_factory.py
│   ├── evidence_factory.py
│   ├── claim_factory.py
│   ├── conflict_factory.py
│   ├── transformation_factory.py
│   ├── artifact_factory.py
│   └── audit_event_factory.py
│
├── unit/
│   ├── __init__.py
│   │
│   ├── domain/
│   │   ├── test_enums.py
│   │   ├── test_value_objects.py
│   │   ├── test_information_unit.py       # Invariant : source_id obligatoire
│   │   ├── test_claim.py                  # Invariant : epistemic_status obligatoire
│   │   ├── test_evidence.py               # Invariant : document_id ou source_id
│   │   ├── test_artifact.py               # Invariant : provenance_complete
│   │   └── test_transformation.py         # Lien input_ids / output_ids
│   │
│   ├── governance/
│   │   ├── test_versioning.py
│   │   ├── test_soft_delete.py
│   │   ├── test_audit_writer.py
│   │   ├── test_budget_enforcer.py
│   │   └── test_gdpr_handler.py
│   │
│   ├── quality/
│   │   ├── test_completeness_check.py
│   │   ├── test_freshness_check.py
│   │   ├── test_provenance_check.py
│   │   ├── test_anomaly_check.py
│   │   ├── test_conflict_detector.py
│   │   └── test_quality_scorer.py
│   │
│   ├── confidence/
│   │   ├── test_confidence_scorer.py
│   │   └── test_confidence_explainer.py
│   │
│   ├── security/
│   │   ├── test_policy_evaluator.py
│   │   ├── test_pii_detector.py
│   │   └── test_permission_checker.py
│   │
│   ├── messaging/
│   │   ├── test_envelope_builder.py
│   │   ├── test_envelope_validator.py
│   │   └── test_idempotency_guard.py
│   │
│   ├── planning/
│   │   ├── test_plan_builder.py
│   │   ├── test_dependency_resolver.py
│   │   ├── test_termination_evaluator.py
│   │   └── test_memory_checker.py
│   │
│   ├── llm/
│   │   ├── test_model_router.py
│   │   ├── test_prompt_hasher.py
│   │   └── test_plan_parser.py
│   │
│   └── core/
│       ├── test_config.py                 # Aucun [CONFIG] codé en dur
│       ├── test_hashing.py
│       └── test_identifiers.py
│
├── integration/
│   ├── __init__.py
│   ├── test_database_connection.py
│   ├── test_migrations.py                 # Up + down sans erreur
│   ├── test_pgvector.py
│   ├── test_fulltext_search.py
│   ├── test_hybrid_search.py
│   ├── test_repositories.py
│   ├── test_versioning_integration.py
│   ├── test_audit_integration.py
│   ├── test_object_storage.py
│   ├── test_redis_cache.py
│   ├── test_circuit_breaker.py
│   ├── test_amqp_broker.py
│   ├── test_agent_registry.py
│   ├── test_idempotency_integration.py
│   ├── test_web_connector.py
│   ├── test_pdf_connector.py
│   └── test_excel_connector.py
│
├── agentic/
│   ├── __init__.py
│   ├── test_single_reliable_source.py
│   ├── test_conflicting_sources.py
│   ├── test_stale_information.py
│   ├── test_insufficient_evidence.py
│   ├── test_tool_unavailable.py
│   ├── test_agent_unavailable.py
│   ├── test_access_denied.py
│   ├── test_ambiguous_request.py
│   ├── test_memory_reuse.py
│   ├── test_data_changed_between_searches.py
│   ├── test_delegation_cycle_detection.py
│   ├── test_budget_exceeded.py
│   ├── test_resume_after_crash.py
│   └── test_non_hallucination.py          # Toute sortie factuelle tracée à une source
│
├── performance/
│   ├── __init__.py
│   ├── test_request_throughput.py
│   ├── test_vector_search_latency.py
│   └── test_concurrent_agents.py
│
└── security/
    ├── __init__.py
    ├── test_auth_bypass.py
    ├── test_injection_prevention.py
    └── test_pii_redaction.py
```

---

## frontend/

```
frontend/
├── package.json
├── vite.config.ts
├── tsconfig.json
├── index.html
│
└── src/
    ├── main.tsx
    ├── App.tsx
    │
    ├── types/
    │   └── index.ts               # Types TypeScript alignés sur les schémas Pydantic
    │
    ├── contexts/
    │   ├── AuthContext.tsx         # Gestion du token JWT et de l'identité agent
    │   └── TraceContext.tsx        # Propagation trace_id dans les requêtes frontend
    │
    ├── hooks/
    │   ├── useRequest.ts           # État et cycle de vie d'une requête
    │   ├── useSSE.ts               # Connexion Server-Sent Events pour la progression
    │   └── useConfidence.ts        # Calcul et affichage du score de confiance
    │
    ├── api/
    │   ├── client.ts              # Client HTTP base avec injection trace
    │   ├── requests.ts
    │   ├── information.ts
    │   ├── sources.ts
    │   ├── evidence.ts
    │   ├── conflicts.ts
    │   ├── artifacts.ts
    │   └── agents.ts
    │
    ├── pages/
    │   ├── SubmitRequest.tsx       # Écran 1 : soumettre une demande
    │   ├── RequestStatus.tsx       # Écran 2 : état + progression temps réel
    │   ├── Sources.tsx             # Écran 3 : sources consultées
    │   ├── ConfidenceMatrix.tsx    # Écran 4 : matrice 7 dimensions
    │   ├── Conflicts.tsx           # Écran 5 : contradictions détectées
    │   ├── InformationUnits.tsx    # Écran 6 : informations extraites
    │   ├── AgentsSolicited.tsx     # Écran 7 : agents sollicités
    │   ├── Traceability.tsx        # Écran 8 : traçabilité complète
    │   └── RequestHistory.tsx      # Écran 9 : historique d'une requête
    │
    └── components/
        ├── ConfidenceBar.tsx       # Barre de score 0-1 colorée
        ├── ProvenanceTree.tsx      # Arbre source → transformation → output
        ├── ConflictCard.tsx        # Carte conflit avec sévérité et statut
        ├── EpistemicBadge.tsx      # Badge fact | hypothesis | assumption | uncertainty
        ├── ProgressStepper.tsx     # Affichage des étapes en temps réel via SSE
        └── AgentCard.tsx           # Carte identité agent avec statut et santé
```

---

## docker/

```
docker/
├── postgres/
│   └── init.sql                   # CREATE EXTENSION vector; pg_trgm; unaccent;
├── rabbitmq/
│   └── rabbitmq.conf              # Configuration vhosts, users, policies DLQ
├── minio/
│   └── init.sh                    # Création buckets inis-artifacts, inis-documents
├── mosquitto/
│   └── mosquitto.conf             # Configuration broker MQTT
├── vault/
│   └── vault.hcl                  # Configuration HashiCorp Vault dev/prod
├── otel/
│   └── otel-collector.yaml        # Pipelines traces, métriques, logs → backends
├── prometheus/
│   └── prometheus.yml             # Scrape config → /v1/metrics
├── grafana/
│   └── dashboards/
│       └── inis_dashboard.json    # Dashboard : métriques, latences, taux d'erreur
└── Dockerfile.dev                 # Python 3.12, dépendances dev, hot reload
```

---

## configs/

```
configs/
├── default.toml                   # Toutes les valeurs [CONFIG] avec documentation inline
├── development.toml               # Surcharges développement local
├── test.toml                      # DB isolée, logs silencieux, mocks activés
└── production.toml                # Template production (sans secrets)
```

---

## scripts/

```
scripts/
├── seed_dev.py                    # Données de développement : agents, sources, requêtes
├── check_invariants.py            # Vérifie les 8 invariants en base existante
├── export_openapi.py              # Génère openapi.json depuis FastAPI
├── generate_changelog.py          # Génère changelog.json depuis migrations et ADR
├── generate_certs.sh              # Génère certificats mTLS pour les agents
├── benchmark.py                   # Benchmarks : throughput, latences, recherche vectorielle
├── backup_db.sh                   # Sauvegarde PostgreSQL avec rotation
└── migrate_rollback.py            # Rollback Alembic avec confirmation interactive
```

---

## deploy/

```
deploy/
├── k8s/
│   ├── namespace.yaml
│   ├── configmap.yaml
│   ├── secrets.yaml               # Template — valeurs injectées par CI/CD
│   ├── deployment.yaml
│   ├── service.yaml
│   ├── ingress.yaml
│   └── hpa.yaml                   # Horizontal Pod Autoscaler
└── helm/
    ├── Chart.yaml
    ├── values.yaml
    └── values.prod.yaml
```

---

## docs/

```
docs/
├── architecture.md                # Vue d'ensemble des composants et flux
├── invariants.md                  # Les 8 invariants avec exemples de violation
├── protocol.md                    # Envelope, 23 types de messages, idempotence
├── confidence.md                  # Formule, 7 dimensions, exemples
├── deployment.md                  # Guide d'installation et de déploiement
├── api_guide.md                   # Guide d'utilisation de l'API HTTP et AMQP
├── security.md                    # mTLS, JWT, PII, politiques d'accès
├── contributing.md                # Conventions de code, règles de couche, tests
├── performance_tuning.md          # Seuils, index, cache, dimensionnement
├── adr/
│   ├── 001_ulid_identifiers.md
│   ├── 002_soft_delete_only.md
│   ├── 003_llm_not_source_of_truth.md
│   ├── 004_hybrid_search_weights.md
│   ├── 005_protocol_versioning.md
│   ├── 006_circuit_breaker_per_connector.md
│   ├── 007_chunked_processing_threshold.md
│   └── 008_budget_dimensions.md
└── changelog.json                 # Machine-readable, exposé sur GET /v1/changelog
```

---

## Règles d'organisation — non négociables

```
app/domain/          → zéro import SQLAlchemy, zéro import httpx, zéro I/O
app/storage/models/  → zéro logique métier, zéro calcul, zéro validation
app/storage/repos/   → seule couche autorisée à écrire du SQL
app/tools/           → signatures et orchestration — les connecteurs font le réseau
app/connectors/      → collecte de données brutes uniquement, zéro logique métier
app/governance/      → appelable depuis toute couche, jamais bloqué par une autre
app/security/        → appelé en premier, avant toute logique métier
app/observability/   → jamais bloquant, jamais en erreur fatale
app/llm/             → jamais source de vérité, toujours encadré par provenance
app/workers/         → consommateurs AMQP, jamais appelés directement par l'API
```

---

## Récapitulatif par zone

| Zone | Fichiers |
|---|---|
| Racine | 11 |
| app/core/ | 6 |
| app/domain/enums/ | 28 |
| app/domain/value_objects/ | 11 |
| app/domain/entities/ | 40 |
| app/domain/interfaces/ | 9 |
| app/agents/ | 12 |
| app/planning/ | 7 |
| app/tools/ | 20 |
| app/connectors/ | 22 |
| app/knowledge/ | 16 |
| app/quality/ | 16 |
| app/confidence/ | 10 |
| app/provenance/ | 3 |
| app/governance/ | 12 |
| app/security/ | 14 |
| app/messaging/ | 16 |
| app/registry/ | 5 |
| app/llm/ | 16 |
| app/artifacts/ | 8 |
| app/workers/ | 4 |
| app/storage/ | 55 |
| app/observability/ | 5 |
| app/api/ | 33 |
| migrations/ | 27 |
| tests/ | 65 |
| frontend/ | 28 |
| docker/ | 11 |
| configs/ | 4 |
| scripts/ | 8 |
| deploy/ | 9 |
| docs/ | 18 |
| **Total** | **~610 fichiers** |

---

**Fin de l'architecture définitive.**
