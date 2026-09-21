# Agent Status

## Dernière mise à jour
2026-09-21 — PHASE-08 clôturée, PHASE-09 à lancer

## Commit de référence
`33777d5` — main

## État des phases

| Phase | Statut | Commit final | Tests | Agents |
|---|---|---|---|---|
| PHASE-01 — Socle multi-agent | ✅ | `34e6a7e` | 67 | 5 |
| PHASE-02 — Agent Runtime | ✅ | `2ca0460` | 111 | 4 |
| PHASE-03 — Transport AMQP/MQTT | ✅ | `5fb159d` | 119 | 1 (OpenCode) |
| PHASE-04 — Information Acquisition | ✅ | `1a6ac5d` | 154 | 4 + intégrateur |
| PHASE-04.2 — Corrections & Convergence | ✅ | `276e8f8` | 158 | 3 + intégrateur |
| PHASE-04.3 — Intégration réelle | ✅ | `c25e2bc` | 169 | 4 + intégrateur |
| PHASE-05 — Knowledge Layer | ✅ | `79500dd` | 209 | 4 + intégrateur |
| PHASE-05.2/05.3/05.4 — Consolidation | ✅ | `fea9262` | 238 | 4 + Codex |
| PHASE-05.5 — Nettoyage dettes | ✅ | `0533316` | 243 (0 skip) | 1 (Codex) |
| PHASE-06 — Quality & Confidence | ✅ | `5c0cca3` | 299 | 4 + intégrateur |
| PHASE-07 — Security | ✅ | `4ed0fa1` | 365 | 4 + intégrateur |
| PHASE-07.4 — Fix FastAPI lazy includes | ✅ | `d0f6fdb` | 359 | 1 (Antigravity) |
| PHASE-08 — Frontend | ✅ | `33777d5` | 374 (+1 skip) | 4 + intégrateur |
| PHASE-09 — Orchestration E2E | 🚀 à lancer | — | — | — |

## État des agents (par phase)

| Agent | Branche | P1 | P2 | P3 | P4 | P5 | P6 | P7 | P8 | P9 |
|---|---|---|---|---|---|---|---|---|---|---|
| Codex | agent/codex/domain | ✅ | ✅ | ⏸️ | ✅ | ✅ | ✅ | ✅ | ✅ | 🚀 |
| Devin | agent/devin/storage | ✅ | ✅ | ⏸️ | ✅ | ✅ | ✅ | ✅ | ✅ | 🚀 |
| OpenCode | agent/opencode/messaging | ✅ | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 🚀 |
| Antigravity | agent/antigravity/api | ✅ | ✅ | ⏸️ | ✅ | ✅ | ✅ | ✅ | ✅ | 🚀 |
| Intégrateur (OpenCode) | agent/cursor/integration | ✅ | ✅ | ⏸️ | ✅ | ✅ | ✅ | ✅ | ✅ | 🚀 |

## Tests
main @ `33777d5` : **374 passed, 1 skipped** (node_modules non commité)

## Emplacements des worktrees

| Agent | Worktree |
|---|---|
| main | C:\Users\LATITUDE 5420\Downloads\inis |
| Codex | C:\Users\LATITUDE 5420\Downloads\INIS-worktrees\codex |
| Devin | C:\Users\LATITUDE 5420\Downloads\INIS-worktrees\devin |
| OpenCode | C:\Users\LATITUDE 5420\Documents\INIS-opencode\opencode |
| Antigravity | C:\Users\LATITUDE 5420\Downloads\INIS-worktrees\antigravity |
| Intégrateur | C:\Users\LATITUDE 5420\Downloads\INIS-worktrees\cursor |

## Dettes techniques ouvertes

**Aucune bloquante.**

### Observations mineures (PHASE-09+)
1. **Test frontend build non vérifié** — `node_modules` non commité. À tester en CI avec `npm install` préalable.
2. **mTLS validator stub** — implémentation complète reportée.
3. **LLM non câblé** — `ModelRouter` retourne une décision mais pas d'appel réel.

## Exceptions documentées

- **PHASE-02** : Codex a couvert `app/registry/` et `app/workers/` (zone OpenCode).
- **PHASE-04** : OpenCode a couvert `app/connectors/api/` + `web/` (zone Devin).
- **PHASE-05.3 → 05.4** : Codex a couvert `migrations/` + `app/connectors/database/` (zone Devin).
- **PHASE-05.5** : Codex a couvert 6 zones pour solder les 7 dettes.
- **PHASE-06** : OpenCode a couvert `app/confidence/` (zone Codex).
- **PHASE-07** : OpenCode a couvert `app/governance/retention/` + `lifecycle/` (zone Devin).
- **PHASE-07.4** : Antigravity a modifié `app/main.py` (mount individuel sous-routers) pour FastAPI 0.141.
- **PHASE-08** : Codex a couvert `frontend/src/types/` (zone Antigravity). OpenCode a couvert `frontend/src/mocks/` (zone Antigravity).

## Règles ajoutées

- **Règle 9** (`AGENT_RULES.md`) : placeholders vides en conflit.
- **Règle 10** (`AGENT_RULES.md`) : migrations Alembic testées `upgrade head` + `downgrade base`.

## Notes de configuration

- **OpenCode** : `C:\Users\LATITUDE 5420\Documents\INIS-opencode\opencode`
- **Intégrateur** : session OpenCode dédiée sur `INIS-worktrees\cursor`
- **FastAPI 0.141.1** : 13 sous-routers montés individuellement dans `app/main.py`
- **Dépendances** : `paho-mqtt`, `trafilatura`, `readability-lxml`, `pgvector`, `numpy`, `aiosqlite`, `msw`
- **Docker Desktop** : requis pour testcontainers
- **Middleware auth** : opt-in `INIS_AUTH_ENABLED=true`
- **Frontend** : `npm install && npm run dev` (proxy `/v1` → localhost:8000)

## Prochaines actions

**PHASE-09 — Orchestration E2E du pipeline agent**

5 agents en parallèle. Objectif : câbler understanding → planning → execution → confidence.

Référence : `INIS_SPEC.md` §7, §8, §22, §28.