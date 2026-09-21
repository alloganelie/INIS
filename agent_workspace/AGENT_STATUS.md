# Agent Status

## Dernière mise à jour
2026-09-21 — PHASE-09 clôturée, PHASE-10 à lancer

## Commit de référence
`<sha final PHASE-09>` — main

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
| PHASE-05.5 — Nettoyage dettes | ✅ | `0533316` | 243 | 1 (Codex) |
| PHASE-06 — Quality & Confidence | ✅ | `5c0cca3` | 299 | 4 + intégrateur |
| PHASE-07 — Security | ✅ | `4ed0fa1` | 365 | 4 + intégrateur |
| PHASE-07.4 — Fix FastAPI lazy includes | ✅ | `d0f6fdb` | 359 | 1 (Antigravity) |
| PHASE-08 — Frontend | ✅ | `33777d5` | 374 | 4 + intégrateur |
| PHASE-09 — Orchestration E2E | ✅ | `<sha final>` | 415+ | 4 + intégrateur |
| PHASE-10 — Extensions | 🚀 à lancer | — | — | — |

## État des agents (par phase)

| Agent | Branche | P1 | P2 | P3 | P4 | P5 | P6 | P7 | P8 | P9 | P10 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Codex | agent/codex/domain | ✅ | ✅ | ⏸️ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 🚀 |
| Devin | agent/devin/storage | ✅ | ✅ | ⏸️ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 🚀 |
| OpenCode | agent/opencode/messaging | ✅ | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 🚀 |
| Antigravity | agent/antigravity/api | ✅ | ✅ | ⏸️ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 🚀 |
| Intégrateur (OpenCode) | agent/cursor/integration | ✅ | ✅ | ⏸️ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 🚀 |

## Tests
main @ `<sha final>` : **415+ passed, 2 skipped** (Docker + test_pipeline_runner justifié)

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

### Observations mineures (PHASE-10+)
1. **LLM non câblé à un backend réel** — `ModelRouter.complete()` retourne un stub déterministe sans `LLM_API_KEY`. Pour activer un vrai LLM, définir `LLM_API_KEY`, `LLM_BASE_URL`.
2. **mTLS validator stub** — `app/security/authn/mtls_validator.py` : validation de certificat reportée.
3. **`test_pipeline_runner_imports` skip** — Pas de classe `*Runner` dans `app/` (rôle tenu par `PipelineCoordinator`).
4. **OCR, audio, vidéo, streaming** — Extensions roadmap §35 (Phase 9 de la spec).

## Exceptions documentées

- **PHASE-02** : Codex a couvert `app/registry/` + `app/workers/` (zone OpenCode).
- **PHASE-04** : OpenCode a couvert `app/connectors/api/` + `web/` (zone Devin).
- **PHASE-05.3 → 05.4** : Codex a couvert `migrations/` + `app/connectors/database/`.
- **PHASE-05.5** : Codex a couvert 6 zones pour solder les dettes.
- **PHASE-06** : OpenCode a couvert `app/confidence/` (zone Codex).
- **PHASE-07** : OpenCode a couvert `app/governance/retention/` + `lifecycle/`.
- **PHASE-07.4** : Antigravity a modifié `app/main.py` pour FastAPI 0.141.
- **PHASE-08** : Codex (types) + OpenCode (mocks) ont couvert `frontend/` (zone Antigravity).
- **PHASE-09** : Codex a fixé `test_frontend_buildable` (zone Cursor) pour résoudre le bug npm Windows.

## Règles actives

- **Règle 9** (`AGENT_RULES.md`) : placeholders vides — renommer/remplir, pas de doublon.
- **Règle 10** (`AGENT_RULES.md`) : migrations Alembic testées `upgrade head` + `downgrade base`.

## Configuration

- **OpenCode** : `C:\Users\LATITUDE 5420\Documents\INIS-opencode\opencode`
- **Intégrateur** : session OpenCode sur `INIS-worktrees\cursor`
- **FastAPI 0.141.1** : 13 sous-routers montés individuellement (`app/main.py`)
- **Dépendances** : paho-mqtt, trafilatura, readability-lxml, pgvector, numpy, aiosqlite, msw
- **Docker Desktop** : requis pour testcontainers
- **Auth** : opt-in via `INIS_AUTH_ENABLED=true`
- **Frontend** : `cd frontend && npm install && npm run dev` (proxy /v1 → localhost:8000)

## Prochaines actions

**PHASE-10 — Extensions** (§35 Phase 9) :
- OCR avancé
- Audio
- Vidéo
- Streaming
- Connecteurs additionnels
- Déploiement Cloud
- Exécution sandboxée

**Avant PHASE-10 : tester l'agent INIS de bout en bout** (voir checklist ci-dessous).