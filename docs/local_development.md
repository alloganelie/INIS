# Développement local

Le dépôt `INIS` sert principalement à l'intégration.

Les agents utilisent les worktrees voisins :

```text
../INIS-worktrees/codex
../INIS-worktrees/devin
../INIS-worktrees/opencode
../INIS-worktrees/antigravity
../INIS-worktrees/cursor
```

Commandes utiles :

```powershell
git status
git branch --show-current
git worktree list
git fetch origin --prune
git log --oneline --decorate -10
```
