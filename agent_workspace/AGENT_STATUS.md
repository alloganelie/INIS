# Agent Status

## Dernière mise à jour
2026-09-13 — PHASE-04 clôturée, PHASE-05 à lancer

## Commit de référence
`1a6ac5d` — main

## État des phases

| Phase | Statut | Commit final | Tests | Agents |
|---|---|---|---|---|
| PHASE-01 — Socle multi-agent | ✅ | `34e6a7e` | 67 | 5 |
| PHASE-02 — Agent Runtime | ✅ | `2ca0460` | 111 | 4 |
| PHASE-03 — Transport AMQP/MQTT | ✅ | `5fb159d` | 119 | 1 (OpenCode) |
| PHASE-04 — Information Acquisition | ✅ | `1a6ac5d` | 154 | 4 + intégrateur |
| PHASE-05 — Knowledge Layer | 🚀 à lancer | — | — | — |

## État des agents (par phase)

| Agent | Branche | P1 | P2 | P3 | P4 | P5 |
|---|---|---|---|---|---|---|
| Codex | agent/codex/domain | ✅ | ✅ | ⏸️ | ✅ | 🚀 |
| Devin | agent/devin/storage | ✅ | ✅ | ⏸️ | ✅ | 🚀 |
| OpenCode | agent/opencode/messaging | ✅ | ❌ | ✅ | ✅ | 🚀 |
| Antigravity | agent/antigravity/api | ✅ | ✅ | ⏸️ | ✅ | 🚀 |
| Intégrateur (OpenCode) | agent/cursor/integration | ✅ | ✅ | ⏸️ | ✅ | 🚀 |

## Tests
main @ 1a6ac5d : **154 passed, 1 warning**

## Emplacements des worktrees

| Agent | Worktree |
|---|---|
| main | C:\Users\LATITUDE 5420\Downloads\inis |
| Codex | C:\Users\LATITUDE 5420\Downloads\INIS-worktrees\codex |
| Devin | C:\Users\LATITUDE 5420\Downloads\INIS-worktrees\devin |
| OpenCode | C:\Users\LATITUDE 5420\Documents\INIS-opencode\opencode |
| Antigravity | C:\Users\LATITUDE 5420\Downloads\INIS-worktrees\antigravity |
| Intégrateur | C:\Users\LATITUDE 5420\Downloads\INIS-worktrees\cursor |

## Dettes techniques ouvertes (PHASE-04.2)

1. **`Dataset.schema` warning Pydantic** — champ masque un attribut de `BaseModel`.
   Correcteur : Codex. Effort : 5 min.
   Solution : renommer en `dataset_schema` ou utiliser `model_config = ConfigDict(protected_namespaces=())`.

2. **`CSVConnector.inspect()` compte les lignes vides finales** — 3 records au lieu de 2 avec un `\n` terminal.
   Correcteur : Devin. Effort : 15 min.
   Solution : filtrer les lignes vides dans `inspect()`.

3. **`SourceConnector` redéclaré localement** par OpenCode dans `rest_connector.py` (car `base.py` était vide au moment du travail).
   Correcteurs : Devin + OpenCode. Effort : 30 min.
   Solution : migrer les imports d'OpenCode vers `app/connectors/base.py`.

4. **`SearchResult` / `SearchProvider` redéclarés** dans `provider_router.py` (car domain vide au moment du travail).
   Correcteurs : Codex + OpenCode. Effort : 30 min.
   Solution : créer `app/domain/entities/search_result.py` (Codex), migrer OpenCode.

## Exceptions documentées

- **PHASE-02** : Codex a couvert `app/registry/` et `app/workers/` (zone OpenCode) car OpenCode n'a pas contribué.
- **PHASE-04** : OpenCode a couvert `app/connectors/api/` et `app/connectors/web/` (zone Devin) sous accord explicite. Devin reste owner de `base.py` + `files/` + `database/`. Aucun chevauchement de fichiers.

## Notes de configuration

- **OpenCode** travaille dans `C:\Users\LATITUDE 5420\Documents\INIS-opencode\opencode` (déplacé hors `Downloads` pour éviter les conflits de "dernier dossier ouvert").
- **Intégrateur** : le rôle anciennement tenu par Cursor est repris par une session OpenCode dédiée, utilisant le worktree `INIS-worktrees\cursor` et la branche `agent/cursor/integration`.
- **paho-mqtt** ajouté au `pyproject.toml` par l'humain (PHASE-03).

## Prochaines actions

1. **PHASE-04.2** (recommandée) : corriger les 4 dettes techniques en parallèle.
2. **PHASE-05** : Knowledge Layer (information_units, evidence, pgvector, recherche hybride, mémoire, provenance) — référence `INIS_SPEC.md` §11, §12, §16, §17.