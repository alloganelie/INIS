# PHASE-09 — Résumé factuel (lot 2 : E2E pipeline complet)

Référence spec : INIS_SPEC.md §7 (modèle de demande), §8 (planification autonome),
§22 (LLM et Model Router), §32 (API), §41.12 (traces de décisions).
Point d'intégration Cursor : branche `agent/cursor/integration`.
Zone interdite respectée : aucune modification sous `app/`, `frontend/`, `pyproject.toml`
(observation en lecture seule + sondages `python -c` / httpx ASGI).

## Zones couvertes par ce lot

| Test | Zone observée | État constaté |
|---|---|---|
| `test_understanding_imports` | `app.agents.understanding` | **présent** : RequestParser, InformationRequest (+ ClarificationDetector, ContextEnricher, RequirementExtractor) |
| `test_decision_imports` | `app.agents.decision` | **présent** : TerminationEvaluator, TerminationDecision (+ DelegationDecider, PartialResultPackager) |
| `test_pipeline_coordinator_imports` | `app.agents.pipeline` | **présent** : PipelineCoordinator (orchestre state machine → understanding → planning → exécution → confiance) |
| `test_plan_executor_imports` | `app.planning.plan_executor` | **présent** : PlanExecutor (+ StepSelector, DependencyResolver) |
| `test_iteration_manager_imports` | `app.planning.iteration_manager` | **présent** : IterationManager (cycle §8.3) |
| `test_model_router_complete_method` | `app.llm.router.model_router.ModelRouter` | **`complete` callable constatée** (vérifiée sans appel réseau) |
| `test_llm_tasks_imports` | `app.llm.tasks` | **présentes** : Understanding, Planning, Classification, ConflictDetection, ConfidenceSignal |
| `test_llm_prompts_builders_imports` | `app.llm.prompts` | **callables** : build_understanding, build_planning (+ classification, conflict_detection, confidence_signal) |
| `test_llm_trace_writer_imports` | `app.llm.tracing.llm_trace_writer` | **présent** : LLMTraceWriter (table `llm_decision_trace` §41.12) |
| `test_pipeline_runner_imports` | runner pipeline dédié | **skip justifié : aucun `*Runner` dans `app/`** (voir dettes) |
| `test_termination_evaluator_smoke` | `TerminationEvaluator.evaluate` | **déterministe vérifié** : exigences satisfaites → stop (REQUIREMENTS_SATISFIED), contexte vide → continue |
| `test_request_parser_smoke` | `RequestParser.parse` | **vérifié** : `REQ_*` + objectif conservé |
| `test_state_machine_full_cycle` | `app.agents.runtime.state_machine` | **vérifié** : RECEIVED → UNDERSTANDING → PLANNED → EXECUTING → VERIFYING → DELIVERING → DONE ; transition invalide → ValidationError |
| `test_pipeline_e2e_smoke` | POST `/v1/requests` puis GET état (httpx ASGI, `app.main`) | **vérifié** : 201 (`request_id` `REQ_*`) puis 200 avec même `request_id` |

## Tests ajoutés par ce lot

`tests/integration/test_phase_09_e2e.py` : 14 tests, pattern repris de la phase 07
(`_has_module`, `_has_symbol`, `_import_or_skip`, `_symbol_or_skip`, `_require_symbols`).
HTTP via `httpx.ASGITransport` sur `app.main:app` (aucun serveur requis).
Résultat attendu : 13 passed, 1 skipped (runner absent, motif explicite).

## Statut pipeline

- Chaîne locale complète et instanciable sans réseau : parse → state machine → termination.
- Chaîne HTTP : création + lecture de demande fonctionnelles (201/200).
- `ModelRouter.complete` non invoquée ici (aurait exigé un backend LLM réseau) — existence seule assertée.

## Dettes restantes (propriétaires pressentis)

1. Aucun runner pipeline dédié (`PipelineRunner`/`RequestWorker`) : `app.workers.request_worker`
   est vide, le rôle est tenu par `PipelineCoordinator` — à cadrer (Codex/OpenCode).
2. `ModelRouter.complete` jamais exercée contre un backend réel ou mocké (contrat §22) — Codex.
3. `PipelineCoordinator` end-to-end (avec exécution d'étapes/outils) non couvert ici, imports seuls — Cursor (lot suivant possible).
4. Persistance `llm_decision_trace` (INSERT) non exercée, import seul — Codex/Devin.
5. Progression/événements SSE (`GET /v1/requests/{id}/progress`, events) non couverts — Cursor.
