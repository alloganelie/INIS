# PHASE-02 — Plan (état visé, non atteint)

Source : `agent_workspace/CURRENT_PHASE.md` (PHASE-02 — Agent Runtime, en cours), `AGENT_ASSIGNMENTS.md`, `INIS_SPEC.md` §35 Phase 2, §33.1 / §33.2.

Objectif documenté de PHASE-02 : runtime agentique — compréhension, planification, tool calling, model router, états, itérations, budgets (`INIS_SPEC.md` §8, §22, §35 Phase 2).

Ce document décrit les **cibles** et les **tests attendus**. Il ne déclare aucun livrable PHASE-02 comme atteint.

## Zones ciblées par agent

Attribution par défaut (`AGENT_ASSIGNMENTS.md`) alignée sur §35 Phase 2 :

| Agent | Zones ciblées | Cible PHASE-02 (§35) |
|---|---|---|
| Codex | `app/agents/`, `app/planning/`, `app/llm/` | compréhension, planning, états, itérations, budgets, model router |
| Devin | `app/tools/` | tool calling (registre d’outils) |
| OpenCode | `app/registry/`, `app/workers/` | registry / heartbeats (socle réseau encore listé en Phase 3 §35 ; workers de heartbeat visés par le lot d’intégration) |
| Antigravity | `app/api/`, `frontend/` | hors cœur runtime §35 Phase 2 ; zone API/UI inchangée dans la matrice |
| Cursor | `tests/integration/`, `docs/` | smokes d’import et pipeline demande → Envelope |

Chemins d’import visés par l’architecture. Des fichiers vides peuvent déjà exister dans le worktree ; les smokes skippent tant que le symbole public n’est pas exporté :

- `app.agents.runtime.state_machine.StateMachine`
- `app.agents.runtime.budget_tracker.BudgetTracker`
- `app.planning.plan_builder.PlanBuilder`
- `app.llm.router.model_router.ModelRouter`
- `app.tools.registry.ToolRegistry`
- `app.registry.agent_registry.AgentRegistry`
- `app.workers.heartbeat_worker.HeartbeatWorker`

## Tests attendus

### Ce lot Cursor (intégration)

- `tests/integration/test_phase_02_e2e.py` : smokes d’import runtime / router / registry / workers ; skip si le module n’existe pas encore.
- `tests/integration/test_phase_02_pipeline.py` : `request_id` ULID `REQ_` emballé dans une Envelope `INFORMATION_REQUEST`, cohérence payload / identifiants.

### §33.1 Unitaires (attendus, non revendiqués ici)

parsing, validation, provenance, scoring, policy, versioning, détection de conflit — à couvrir par les propriétaires de zone quand le runtime existe.

### §33.2 Intégration (attendus, non revendiqués ici)

PostgreSQL, pgvector, object storage, RabbitMQ, MQTT, connecteurs, agent registry — hors smoke d’import de ce lot ; `test_registry_smoke` n’est qu’un import, pas un test d’infra.

## Hors périmètre de ce document

Aucun critère « PHASE-02 terminée ». `AGENT_STATUS.md` indique le démarrage PHASE-02 et renvoie à `CURRENT_PHASE.md` pour le Lot 1 par agent.
