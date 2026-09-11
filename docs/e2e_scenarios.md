# Scénarios E2E

## Tâche normale
Issue → attribution → worktree → implémentation → tests → commit → push → PR → CI → revue → merge.

## Changement contractuel
Change Request → analyse d'impact → modification → tests de compatibilité → PR → validation → merge.

## Conflit
Les worktrees isolent les agents. Le conflit est traité à l'intégration, sans écraser silencieusement le travail d'un autre agent.

## Agent indisponible
Reprise après handoff explicite.
