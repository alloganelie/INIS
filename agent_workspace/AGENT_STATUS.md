# Agent Status

## Dernière mise à jour
2026-09-13 — PHASE-05 clôturée, PHASE-06 à lancer

## Commit de référence
<sha final PHASE-05> — main

## État des phases

| Phase | Statut | Commit final | Tests | Agents |
|---|---|---|---|---|
| PHASE-01 — Socle multi-agent | ✅ | `34e6a7e` | 67 | 5 |
| PHASE-02 — Agent Runtime | ✅ | `2ca0460` | 111 | 4 |
| PHASE-03 — Transport AMQP/MQTT | ✅ | `5fb159d` | 119 | 1 (OpenCode) |
| PHASE-04 — Information Acquisition | ✅ | `1a6ac5d` | 154 | 4 + intégrateur |
| PHASE-04.2 — Corrections & Convergence | ✅ | `276e8f8` | 158 | 3 + intégrateur |
| PHASE-04.3 — Intégration réelle | ✅ | `c25e2bc` | 169 | 4 + intégrateur |
| PHASE-05 — Knowledge Layer | ✅ | `<sha final>` | 209 | 4 + intégrateur |
| PHASE-06 — Quality & Confidence | 🚀 à lancer | — | — | — |

## État des agents (par phase)

| Agent | Branche | P1 | P2 | P3 | P4 | P4.2 | P4.3 | P5 | P6 |
|---|---|---|---|---|---|---|---|---|---|
| Codex | agent/codex/domain | ✅ | ✅ | ⏸️ | ✅ | ✅ | ✅ | ✅ | 🚀 |
| Devin | agent/devin/storage | ✅ | ✅ | ⏸️ | ✅ | ✅ | ✅ | ✅ | 🚀 |
| OpenCode | agent/opencode/messaging | ✅ | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | 🚀 |
| Antigravity | agent/antigravity/api | ✅ | ✅ | ⏸️ | ✅ | ⏸️ | ✅ | ✅ | 🚀 |
| Intégrateur (OpenCode) | agent/cursor/integration | ✅ | ✅ | ⏸️ | ✅ | ⏸️ | ✅ | ✅ | 🚀 |

## Tests
main @ <sha final> : **209 passed, 0 warning, 0 skipped**

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

1. **PostgresConnector stub partiel** — structure prête (utilise engine.py) mais pas de connexion réelle.
   Correcteur : Devin. Effort : 45 min.

2. **Classes de recherche (VectorSearch, HybridSearch, FullTextSearch) en stub** — retournent listes vides.
   Correcteur : Devin. Effort : 1 h 30.

3. **AuditWriter en mémoire** — événements non persistants.
   Correcteur : Codex. Effort : 30 min.

4. **HealthAggregator sans checks enregistrés** — câblage postgres/redis/broker à faire.
   Correcteur : OpenCode. Effort : 30 min.

5. **ChunkSplitter approximatif** — utilise des mots comme approximation de tokens.
   Correcteur : Codex. Effort : 30 min.

6. **LineageTracker non persistant** — graphe en mémoire uniquement.
   Correcteur : Codex. Effort : 30 min.

7. **`readability_extractor.py` vide** — extractor alternatif non implémenté.
   Correcteur : OpenCode. Effort : 20 min.

8. **Tests d'intégration sans vraie DB PostgreSQL** — 209 tests unitaires/E2E mais aucun contre une DB réelle.
   Correcteur : Devin. Effort : 1 h (testcontainers + migrations 0002/0003).

9. **Trafilatura non testée avec vraie lib** — fallback regex testé, pas l'extraction réelle.
   Correcteur : OpenCode. Effort : 15 min.

## Exceptions documentées

- **PHASE-02** : Codex a couvert `app/registry/` et `app/workers/` (zone OpenCode) car OpenCode n'a pas contribué.
- **PHASE-04** : OpenCode a couvert `app/connectors/api/` et `app/connectors/web/` (zone Devin) sous accord explicite. Devin reste owner de `base.py` + `files/` + `database/`. Aucun chevauchement de fichiers.

## Notes de configuration

- **OpenCode** travaille dans `C:\Users\LATITUDE 5420\Documents\INIS-opencode\opencode` (déplacé hors `Downloads` pour éviter les conflits de "dernier dossier ouvert").
- **Intégrateur** : rôle tenu par une session OpenCode dédiée, utilisant le worktree `INIS-worktrees\cursor` et la branche `agent/cursor/integration`.
- **paho-mqtt** ajouté au `pyproject.toml` par l'humain (PHASE-03).
- **trafilatura** + **readability-lxml** ajoutés au `pyproject.toml` par l'humain (PHASE-04.3).
- **pgvector** + **numpy** ajoutés au `pyproject.toml` par l'humain (PHASE-05).

## Prochaines actions

1. **PHASE-06 — Quality & Confidence** : contrôles qualité, contradictions, scoring, matrice de confiance, fraîcheur.
   Référence : `INIS_SPEC.md` §13, §14, §15.
2. Les 9 dettes techniques ci-dessus peuvent être traitées en parallèle ou en PHASE-06 selon les besoins.