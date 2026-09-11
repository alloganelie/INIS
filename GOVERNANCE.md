# INIS — Documentation de gouvernance du développement

Ce dossier contient les documents opérationnels utilisés pour développer INIS avec plusieurs agents de coding : Codex, Devin, Antigravity, Cursor et OpenCode.

## Documents

- `CODING_RULES.md` — règles générales de code.
- `NAMING.md` — nomenclature canonique des fichiers, symboles, IDs et concepts.
- `CONTRACTS.md` — contrats stables entre modules et agents.
- `AGENT_RULES.md` — règles impératives pour les agents de coding.
- `AGENT_ASSIGNMENTS.md` — matrice de propriété des zones et responsabilités par agent.
- `GIT_WORKFLOW.md` — stratégie Git/GitHub, branches, commits, PR et merge.
- `PHASE_WORKFLOW.md` — cycle officiel d'une phase de développement.
- `CHANGE_REQUESTS.md` — procédure pour demander une modification hors zone.
- `DEFINITION_OF_DONE.md` — critères de validation avant merge et avant clôture de phase.
- `TESTING.md` — stratégie de tests et portes de validation.
- `DEPENDENCY_RULES.md` — règles de dépendances et d'importations.
- `SECURITY_RULES.md` — règles minimales de sécurité applicables au code.
- `CHANGELOG.md` — historique humain des changements importants.
- `templates/AGENT_TASK.md` — modèle de mission à donner à un agent.
- `templates/CHANGE_REQUEST.md` — modèle de demande de changement inter-zone.
- `templates/PHASE_REPORT.md` — modèle de rapport de fin de phase.

## Règle centrale

L'architecture est la source de vérité structurelle. Les présents documents gouvernent le travail des agents autour de cette architecture. Aucun agent ne doit redéfinir l'architecture de sa propre initiative.
