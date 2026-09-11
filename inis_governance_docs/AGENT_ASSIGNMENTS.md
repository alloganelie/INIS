# INIS — Agent Assignments

Ce document définit la propriété de code. Il peut être modifié au début d'une phase, mais une zone ne doit avoir qu'un seul propriétaire principal à un instant donné.

## Agents disponibles

- Codex
- Devin
- Antigravity
- Cursor
- OpenCode

## Règle d'attribution

Un agent principal possède une zone. Les autres agents peuvent la lire mais ne la modifient pas sans autorisation.

## Attribution recommandée par défaut

| Zone | Propriétaire principal | Rôle recommandé |
|---|---|---|
| `app/core/` | Codex | fondations et contrats internes |
| `app/domain/` | Codex | modèle métier et interfaces |
| `app/storage/` | Devin | PostgreSQL, modèles, repositories |
| `migrations/` | Devin | schéma persistant |
| `app/agents/` | Codex | runtime agentique |
| `app/planning/` | Codex | planification |
| `app/messaging/` | OpenCode | AMQP/MQTT/protocole |
| `app/registry/` | OpenCode | découverte et santé des agents |
| `app/connectors/` | Devin | accès techniques aux sources |
| `app/tools/` | Devin | outils et intégrations techniques |
| `app/knowledge/` | Codex | extraction, connaissance et recherche |
| `app/quality/` | Codex | qualité et conflits |
| `app/confidence/` | Codex | confiance |
| `app/provenance/` | Codex | traçabilité |
| `app/governance/` | Devin | politiques et gouvernance technique |
| `app/security/` | Devin | sécurité |
| `app/llm/` | Codex | routage et usage encadré des LLM |
| `app/artifacts/` | Devin | artefacts et stockage objet |
| `app/workers/` | OpenCode | workers et consommation AMQP |
| `app/api/` | Antigravity | API HTTP |
| `app/observability/` | OpenCode | télémétrie et monitoring |
| `frontend/` | Antigravity | interface |
| `tests/` | partagé selon zone, intégration par Cursor | validation |
| `docker/` | Devin | infrastructure locale |
| `deploy/` | Devin | déploiement |
| `configs/` | Devin | configuration |
| `scripts/` | Devin | scripts opérationnels |

Cette matrice est une attribution initiale. La branche de phase fait foi lorsqu'une attribution temporaire est définie.

## Rôle particulier de Cursor

Cursor est recommandé comme agent de revue, de correction ciblée et d'intégration locale plutôt que comme propriétaire par défaut d'une grande zone. Il peut devenir propriétaire d'une zone lors d'une phase si cela est explicitement défini.

## Intégrateur

Chaque phase doit nommer un intégrateur. L'intégrateur ne merge pas une branche dont les tests obligatoires échouent.
