# Workflow multi-agents INIS

Les agents sont des applications locales.

```text
INIS/                         # intégration
INIS-worktrees/
  codex/                      # Codex
  devin/                      # Devin
  opencode/                   # OpenCode
  antigravity/                # Antigravity
  cursor/                     # Cursor
        ↓
     Git push
        ↓
     GitHub PR
        ↓
 GitHub Actions
        ↓
 revue / merge
        ↓
      main
```

GitHub Actions valide le code du dépôt ; il ne lance pas les applications desktop locales.

Cycle :
1. tâche ;
2. attribution ;
3. travail dans worktree ;
4. tests ;
5. commit ;
6. push ;
7. PR ;
8. CI ;
9. revue ;
10. merge.

Cursor reste principalement l'agent de revue/intégration/corrections ciblées.
