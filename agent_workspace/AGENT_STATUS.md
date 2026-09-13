# Agent Status

## Dernière mise à jour
2026-09-13 — PHASE-05.2/05.3/05.4 clôturées, PHASE-06 à lancer

## Commit de référence
`<sha final PHASE-05.4>` — main

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
| PHASE-05.2 — Consolidation infra | ✅ | `<sha>` | 238 (+1 skip) | 4 + intégrateur |
| PHASE-05.3 — Fix Alembic + PostgresConnector | ✅ | `<sha>` | 238 (+1 skip) | 1 (Devin, échec) |
| PHASE-05.4 — Fix exceptionnel zone Devin (Codex) | ✅ | `43f7841` | 233 → 238 | 1 (Codex) |
| PHASE-06 — Quality & Confidence | 🚀 à lancer | — | — | — |

## État des agents (par phase)

| Agent | Branche | P1 | P2 | P3 | P4 | P4.2 | P4.3 | P5 | P5.2 | P5.3 | P5.4 | P6 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Codex | agent/codex/domain | ✅ | ✅ | ⏸️ | ✅ | ✅ | ✅ | ✅ | ✅ | ⏸️ | ✅ | 🚀 |
| Devin | agent/devin/storage | ✅ | ✅ | ⏸️ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ⏸️ | 🚀 |
| OpenCode | agent/opencode/messaging | ✅ | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ⏸️ | ⏸️ | 🚀 |
| Antigravity | agent/antigravity/api | ✅ | ✅ | ⏸️ | ✅ | ⏸️ | ✅ | ✅ | ✅ | ⏸️ | ⏸️ | 🚀 |
| Intégrateur (OpenCode) | agent/cursor/integration | ✅ | ✅ | ⏸️ | ✅ | ⏸️ | ✅ | ✅ | ✅ | ⏸️ | ⏸️ | 🚀 |

## Tests
main @ `<sha final>` : **238 passed, 1 skipped** (le skip est justifié — voir Dettes #1)

## Emplacements des worktrees

| Agent | Worktree |
|---|---|
| main | C:\Users\LATITUDE 5420\Downloads\inis |
| Codex | C:\Users\LATITUDE 5420\Downloads\INIS-worktrees\codex |
| Devin | C:\Users\LATITUDE 5420\Downloads\INIS-worktrees\devin |
| OpenCode | C:\Users\LATITUDE 5420\Documents\INIS-opencode\opencode |
| Antigravity | C:\Users\LATITUDE 5420\Downloads\INIS-worktrees\antigravity |
| Intégrateur | C:\Users\LATITUDE 5420\Downloads\INIS-worktrees\cursor |

## Dettes techniques ouvertes (reportées PHASE-06)

1. **`SourceRepository` — décision architecturale en attente** ⚠️
   - Emplacement vide : `app/storage/repositories/source_repository.py`
   - Emplacement actuel : `app/api/v1/sources/repository.py` (créé par Antigravity)
   - Le test `test_source_repository_with_db` skip car il cherche dans `app/storage/repositories/`
   - **Action** : décider où vit le repository (storage vs api) puis aligner le test
   - **Correcteur** : Devin (storage) + Antigravity (api) + Intégrateur (test)

2. **Schéma §27 partiel**
   - Migrations 0001-0004 couvrent : agents, sources, documents, information_units, audit_events, embeddings, transformations
   - Manquants : claims, conflicts, artifacts, artifact_versions, artifact_lineage, agent_messages, execution_checkpoints, budget_usage, progress, access_policies, security_classifications
   - **Correcteur** : Devin. Effort : 2 h.

3. **AuditWriter en mémoire**
   - Événements non persistants malgré la table `audit_events` créée
   - **Correcteur** : Codex. Effort : 30 min.

4. **HealthAggregator sans câblage lifecycle**
   - Les checks postgres/redis/broker ne sont pas branchés automatiquement au démarrage
   - **Correcteur** : OpenCode. Effort : 30 min.

5. **DeprecationWarning `testcontainers.postgres`**
   - Remplacer par `testcontainers.community.postgres`
   - **Correcteur** : Devin. Effort : 10 min.

6. **PostgresConnector mode dégradé**
   - Retourne `[]` si pas de DB — pas de test réel pour le mode connecté
   - **Correcteur** : Devin. Effort : 20 min.

7. **`readability_extractor.py` non testé avec vraie lib**
   - Fallback regex testé, extraction réelle non couverte
   - **Correcteur** : OpenCode. Effort : 15 min.

## Exceptions documentées

- **PHASE-02** : Codex a couvert `app/registry/` et `app/workers/` (zone OpenCode) car OpenCode n'a pas contribué.
- **PHASE-04** : OpenCode a couvert `app/connectors/api/` et `app/connectors/web/` (zone Devin) sous accord explicite. Devin reste owner de `base.py` + `files/` + `database/`.
- **PHASE-05.3 → 05.4** : Devin a échoué 2 fois à faire fonctionner `alembic upgrade head`. Codex est intervenu sur :
  - `migrations/` + `alembic.ini` (zone Devin)
  - `app/connectors/database/` (zone Devin)
  - `tests/integration/` (zone Cursor)
  - Fix final : `DATABASE_URL` lue dans `env.py`, credentials retirées de `alembic.ini`, `latency_ms` toujours numérique dans `PostgresConnector.health_check()`.

## Règles ajoutées

- **Règle 9** (`AGENT_RULES.md`) : gestion des placeholders vides en conflit (renommer/remplir, ne pas créer de doublon).
- **Règle 10** (`AGENT_RULES.md`) : tout agent qui crée/modifie une migration Alembic DOIT tester `upgrade head` + `downgrade base` sur une vraie DB avant de commit.

## Notes de configuration

- **OpenCode** travaille dans `C:\Users\LATITUDE 5420\Documents\INIS-opencode\opencode` (isolé de `Downloads` pour éviter les conflits de "dernier dossier ouvert").
- **Intégrateur** : rôle tenu par une session OpenCode dédiée sur `INIS-worktrees\cursor`, branche `agent/cursor/integration`.
- **Dépendances ajoutées par l'humain** au `pyproject.toml` :
  - `paho-mqtt` (PHASE-03)
  - `trafilatura` + `readability-lxml` (PHASE-04.3)
  - `pgvector` + `numpy` (PHASE-05)
  - `aiosqlite` (PHASE-05.2)
- **Docker Desktop** : doit être lancé pour les tests testcontainers.

## Prochaines actions

Deux options :

**Option A — PHASE-05.5 (dettes techniques) — recommandée**
Traiter les 7 dettes ci-dessus en 2-3 lots. Durée : ~2 h.
Résultat : projet 100% propre, 0 skip, 0 warning.

**Option B — PHASE-06 (Quality & Confidence)**
- Contrôles qualité (§13)
- Détection de contradictions (§14.4)
- Modèle de confiance (§15)
Durée : ~3 h.
Report de dettes : risque d'accumulation.