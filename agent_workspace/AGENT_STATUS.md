# Agent Status

## Dernière mise à jour
2026-09-14 — PHASE-06 clôturée, PHASE-07 à lancer

## Commit de référence
`<sha final PHASE-06>` — main

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
| PHASE-06 — Quality & Confidence | ✅ | `<sha final>` | 299 (0 skip) | 4 + intégrateur |
| PHASE-07 — Security | 🚀 à lancer | — | — | — |

## État des agents (par phase)

| Agent | Branche | P1 | P2 | P3 | P4 | P4.2 | P4.3 | P5 | P5.2-4 | P5.5 | P6 | P7 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Codex | agent/codex/domain | ✅ | ✅ | ⏸️ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 🚀 |
| Devin | agent/devin/storage | ✅ | ✅ | ⏸️ | ✅ | ✅ | ✅ | ✅ | ✅ | ⏸️ | ✅ | 🚀 |
| OpenCode | agent/opencode/messaging | ✅ | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ⏸️ | ✅ | 🚀 |
| Antigravity | agent/antigravity/api | ✅ | ✅ | ⏸️ | ✅ | ⏸️ | ✅ | ✅ | ✅ | ⏸️ | ✅ | 🚀 |
| Intégrateur (OpenCode) | agent/cursor/integration | ✅ | ✅ | ⏸️ | ✅ | ⏸️ | ✅ | ✅ | ✅ | ⏸️ | ✅ | 🚀 |

## Tests
main @ `<sha final>` : **299 passed, 0 skipped, 0 failed, 0 warning**

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

**Aucune bloquante.** PHASE-06 soldée à 299 tests, 0 skip, 0 failed.

### Observations mineures (PHASE-07+)
1. **Formules intra-dimension confidence** — `source_freshness` (365j linéaire) et neutre 0.5 pour dimensions indéterminées. §15 ne spécifie pas ces formules → à valider métier.
2. **`quality_scorer` valeurs par défaut** — poids §13.3 conformes. Aucune dette.
3. **`DuplicatesCheck`** — livré en PHASE-06.2 (commit `334cbb8`).

## Exceptions documentées

- **PHASE-02** : Codex a couvert `app/registry/` et `app/workers/` (zone OpenCode) car OpenCode n'a pas contribué.
- **PHASE-04** : OpenCode a couvert `app/connectors/api/` et `app/connectors/web/` (zone Devin) sous accord explicite.
- **PHASE-05.3 → 05.4** : Devin a échoué 2 fois sur `alembic upgrade head`. Codex est intervenu sur `migrations/`, `alembic.ini`, `app/connectors/database/`, `tests/integration/`.
- **PHASE-05.5** : Codex a couvert 6 zones (Devin × 3, Antigravity × 1, OpenCode × 2, Cursor × 1) pour solder les 7 dettes techniques.
- **PHASE-06** : OpenCode a couvert `app/confidence/` (zone Codex) sous accord explicite. Codex était chargé sur `app/domain/entities/conflict.py` + `app/quality/checks/` (11 checks).

## Règles ajoutées

- **Règle 9** (`AGENT_RULES.md`) : gestion des placeholders vides en conflit (renommer/remplir, ne pas créer de doublon).
- **Règle 10** (`AGENT_RULES.md`) : tout agent qui crée/modifie une migration Alembic DOIT tester `upgrade head` + `downgrade base` sur une vraie DB avant commit.

## Notes de configuration

- **OpenCode** travaille dans `C:\Users\LATITUDE 5420\Documents\INIS-opencode\opencode` (isolé).
- **Intégrateur** : session OpenCode dédiée sur `INIS-worktrees\cursor`, branche `agent/cursor/integration`.
- **Dépendances ajoutées par l'humain** au `pyproject.toml` :
  - `paho-mqtt` (PHASE-03)
  - `trafilatura` + `readability-lxml` (PHASE-04.3)
  - `pgvector` + `numpy` (PHASE-05)
  - `aiosqlite` (PHASE-05.2)
- **Docker Desktop** : requis pour tests testcontainers (PostgreSQL 16 + pgvector).

## Prochaines actions

**PHASE-07 — Security** (référence `INIS_SPEC.md` §19, §20, §41.9).

5 agents en parallèle :
- **Codex** : `app/domain/entities/` (AccessPolicy, SecurityClassification) + `app/governance/audit/` (renforcement)
- **Devin** : `app/security/` (authn mTLS/JWT/API keys, authz RBAC+ABAC, PII, rate limiting, vault)
- **OpenCode** : `app/governance/` (policy_loader, retention, GDPR handler) + `app/observability/tracing.py`
- **Antigravity** : `app/api/v1/system/` (health/ready étendu) + middleware d'auth sur endpoints
- **Intégrateur** : `tests/integration/test_phase_07_e2e.py` + `docs/phase_07_summary.md`

Objectifs clés PHASE-07 :
1. Authentication (mTLS inter-agents, JWT HTTP, API keys admin) — §19.2
2. Authorization RBAC + ABAC — §19.3
3. Classification PII — §19.4
4. Vault credentials — §41.4
5. Audit renforcé (before_hash, after_hash) — §20.1
6. Rate limiting — §19 (extension)