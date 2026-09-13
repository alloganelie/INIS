# Current Phase

## PHASE-01 — Stabilisation du socle multi-agent — ✅ TERMINÉE
Date : 2026-09-12 — Commit : 34e6a7e — Tests : 67

## PHASE-02 — Agent Runtime — ✅ TERMINÉE
Date : 2026-09-12 — Commit : 2ca0460 — Tests : 111
Zones : agents/runtime, planning, registry, workers, llm/router, tools, api/v1/*, tests/integration

## PHASE-03 — Transport AMQP/MQTT — ✅ TERMINÉE
Date : 2026-09-13 — Commit : 5fb159d — Tests : 119

### Zones couvertes (OpenCode seul)
- app/messaging/amqp/ : topology, broker, publisher, consumer, health, DLQ (§41.8)
- app/messaging/mqtt/ : broker (stub), health
- pyproject.toml : + paho-mqtt

### Gate PHASE-03 — 6/6 ✅
- [x] Transport AMQP (aio-pika) implémenté
- [x] Retry + DLQ (§41.8)
- [x] MQTT stub prêt
- [x] Tests verts (119 passed)
- [x] CI GitHub verte
- [x] PR mergée

---

## PHASE-04 — Information Acquisition — 🚀 EN COURS

Objectif : connecteurs de sources (web, REST API, fichiers, DB) + domain entities Source/Document/Dataset + endpoints API + tests E2E.

### Zones assignées
| Agent | Zone | Lot |
|---|---|---|
| Codex | app/domain/entities/ | Source, Document, Dataset, SourceCandidate |
| Devin | app/connectors/files/, app/connectors/database/ | base.py + CSV/JSON/Excel + PostgreSQL |
| OpenCode | app/connectors/api/, app/connectors/web/ | REST + auth + web search providers |
| Antigravity | app/api/v1/sources/, app/api/v1/information/ | Endpoints GET/POST |
| Cursor | tests/integration/ | Smoke tests E2E PHASE-04 + doc |

Référence spec : INIS_SPEC.md §9 (Connecteurs), §10 (Web), §35 (Roadmap Phase 4).