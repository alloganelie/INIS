# Current Phase

## PHASE-01 — Stabilisation du socle multi-agent — ✅ TERMINÉE

Date de clôture : 2026-09-12
Commit final : 34e6a7e
Tests : 67 passed

## PHASE-02 — Agent Runtime — ✅ TERMINÉE

Date de clôture : 2026-09-12
Commit final : 2ca0460
Tests : 111 passed (+44)

### Zones couvertes

| Zone | Agent | Fichiers clés | Tests |
|---|---|---|---|
| app/agents/runtime/ | Codex | state_machine, budget_tracker | ✓ |
| app/planning/ | Codex | plan_builder | ✓ |
| app/registry/ | Codex (exception) | agent_registry, capability_index | ✓ |
| app/workers/ | Codex (exception) | heartbeat_worker | ✓ |
| app/llm/router/ | Devin | model_router, cost_tracker, fallback_chain | ✓ |
| app/tools/ | Devin | registry | ✓ |
| app/api/v1/requests/ | Antigravity | schemas, router | ✓ |
| app/api/v1/agents/ | Antigravity | schemas, router | ✓ |
| tests/integration/ | Cursor | phase_02_e2e, phase_02_pipeline | ✓ |
| docs/ | Cursor | phase_02_plan.md | — |

### Exceptions documentées
- OpenCode n'a pas contribué à PHASE-02. Codex a couvert `app/registry/` et `app/workers/` à sa place.
- ULID_PREFIXES complété avec `PLAN_`, `STEP_`, `ITER_` (manquants §0.3).

---

## PHASE-03 — Transport AMQP/MQTT — 🚀 EN COURS

Objectif : implémenter la couche de transport AMQP (aio-pika) et MQTT (interface).

### Lot en cours — OpenCode
- `app/messaging/amqp/` : broker, publisher, consumer, topology, health, DLQ
- `app/messaging/mqtt/` : broker, health

Référence spec : `INIS_SPEC.md` §4.4 (broker), §5.2 (types), §41.8 (retry).