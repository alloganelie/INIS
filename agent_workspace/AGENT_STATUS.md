# Agent Status

## Dernière mise à jour
2026-09-21 — PHASE-07 clôturée, PHASE-08 à lancer

## Commit de référence
`<sha final PHASE-07>` — main

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
| PHASE-05.2/05.3/05.4 — Consolidation | ✅ | `fea9262` | 238 (+1 skip) | 4 + Codex |
| PHASE-05.5 — Nettoyage dettes | ✅ | `0533316` | 243 (0 skip) | 1 (Codex) |
| PHASE-06 — Quality & Confidence | ✅ | `5c0cca3` | 299 (0 skip) | 4 + intégrateur |
| PHASE-07 — Security | ✅ | `<sha final>` | 365+ (13 skip Docker) | 4 + intégrateur |
| PHASE-07.4 — Fix FastAPI lazy includes | ✅ | `d0f6fdb` | 359+ | 1 (Antigravity) |
| PHASE-08 — Frontend | 🚀 à lancer | — | — | — |

## État des agents (par phase)

| Agent | Branche | P1 | P2 | P3 | P4 | P4.2 | P4.3 | P5 | P5.2-4 | P5.5 | P6 | P7 | P7.4 | P8 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Codex | agent/codex/domain | ✅ | ✅ | ⏸️ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ⏸️ | 🚀 |
| Devin | agent/devin/storage | ✅ | ✅ | ⏸️ | ✅ | ✅ | ✅ | ✅ | ✅ | ⏸️ | ✅ | ✅ | ⏸️ | 🚀 |
| OpenCode | agent/opencode/messaging | ✅ | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ⏸️ | ✅ | ✅ | ⏸️ | 🚀 |
| Antigravity | agent/antigravity/api | ✅ | ✅ | ⏸️ | ✅ | ⏸️ | ✅ | ✅ | ✅ | ⏸️ | ✅ | ✅ | ✅ | 🚀 |
| Intégrateur (OpenCode) | agent/cursor/integration | ✅ | ✅ | ⏸️ | ✅ | ⏸️ | ✅ | ✅ | ✅ | ⏸️ | ✅ | ✅ | ⏸️ | 🚀 |

## Tests
main @ `<sha final>` : **365+ passed, 0 failed, 13 skipped** (Docker non disponible en local)

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

### Observations mineures (PHASE-08+)
1. **Skips Docker (13)** — tests testcontainers skippent si Docker Desktop n'est pas lancé. À exécuter en CI ou en local avec Docker.
2. **mTLS validator** — implémentation stub V1 (`app/security/authn/mtls_validator.py`). Validation de certificat complète reportée.
3. **Formulaire frontend** — à venir en PHASE-08.

## Exceptions documentées

- **PHASE-02** : Codex a couvert `app/registry/` et `app/workers/` (zone OpenCode) car OpenCode n'a pas contribué.
- **PHASE-04** : OpenCode a couvert `app/connectors/api/` et `app/connectors/web/` (zone Devin) sous accord explicite.
- **PHASE-05.3 → 05.4** : Devin a échoué 2 fois sur `alembic upgrade head`. Codex est intervenu sur `migrations/`, `alembic.ini`, `app/connectors/database/`, `tests/integration/`.
- **PHASE-05.5** : Codex a couvert 6 zones (Devin × 3, Antigravity × 1, OpenCode × 2, Cursor × 1) pour solder les 7 dettes.
- **PHASE-06** : OpenCode a couvert `app/confidence/` (zone Codex) sous accord explicite.
- **PHASE-07** : OpenCode a couvert `app/governance/retention/` + `app/governance/lifecycle/` (zone Devin) sous accord explicite.
- **PHASE-07.4** : Antigravity a modifié `app/main.py` (mount individuel des sous-routers) pour contourner le bug FastAPI 0.141 lazy includes.

## Règles ajoutées

- **Règle 9** (`AGENT_RULES.md`) : gestion des placeholders vides en conflit (renommer/remplir, ne pas créer de doublon).
- **Règle 10** (`AGENT_RULES.md`) : tout agent qui crée/modifie une migration Alembic DOIT tester `upgrade head` + `downgrade base` sur une vraie DB avant commit.

## Notes de configuration

- **OpenCode** travaille dans `C:\Users\LATITUDE 5420\Documents\INIS-opencode\opencode` (isolé).
- **Intégrateur** : session OpenCode dédiée sur `INIS-worktrees\cursor`, branche `agent/cursor/integration`.
- **FastAPI 0.141.1** : montage individuel des 13 sous-routers dans `app/main.py` (les `_IncludedRouter` paresseux cassent le montage agrégé).
- **Dépendances ajoutées par l'humain** au `pyproject.toml` :
  - `paho-mqtt` (PHASE-03)
  - `trafilatura` + `readability-lxml` (PHASE-04.3)
  - `pgvector` + `numpy` (PHASE-05)
  - `aiosqlite` (PHASE-05.2)
- **Docker Desktop** : requis pour tests testcontainers (PostgreSQL 16 + pgvector).
- **Middleware auth** : opt-in via `INIS_AUTH_ENABLED=true` (désactivé par défaut pour ne pas casser les tests existants).

## Prochaines actions

**PHASE-08 — Frontend** (référence `INIS_SPEC.md` §31).

Zone : `frontend/`
Stack cible : React + Vite + TypeScript

9 écrans obligatoires §31.1 :
1. Soumettre une demande
2. Voir l'état d'une recherche
3. Visualiser les sources
4. Consulter la matrice de confiance
5. Consulter les contradictions
6. Voir les informations extraites
7. Voir les agents sollicités
8. Consulter la traçabilité
9. Consulter l'historique d'une requête

Écran de confiance §31.2 : visualisation des 7 dimensions.