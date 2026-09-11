# Développement avec les agents

Avant toute tâche, l'agent lit :

- `inis_governance_docs/README.md`
- `inis_governance_docs/AGENT_RULES.md`
- `inis_governance_docs/AGENT_ASSIGNMENTS.md`
- `inis_governance_docs/DEFINITION_OF_DONE.md`
- `agent_workspace/CURRENT_PHASE.md`
- `agent_workspace/AGENT_WORKSPACE_PROTOCOL.md`

Il vérifie `git status`, reste dans sa zone et ne modifie pas les contrats publics sans Change Request.

À la fin : tests + commit + rapport de handoff.
