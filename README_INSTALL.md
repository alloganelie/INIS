# INIS — Multi-Agent Local Development Package

Ce package configure le workflow local pour Codex, Devin, OpenCode, Antigravity et Cursor.

## Principe

Les cinq agents sont des applications locales qui écrivent sur ton ordinateur. GitHub sert de dépôt distant, de revue, d'historique et de CI.

```text
PC
├── INIS/                         # intégration
└── INIS-worktrees/
    ├── codex/                    # Codex
    ├── devin/                    # Devin
    ├── opencode/                 # OpenCode
    ├── antigravity/              # Antigravity
    └── cursor/                   # Cursor
              ↓
          Git / branches
              ↓
        GitHub / PR / CI
```

Ne fais pas travailler plusieurs agents dans le même dossier physique.

## Installation

```powershell
Expand-Archive .\INIS_MULTI_AGENT_PACKAGE.zip -DestinationPath .\INIS_MULTI_AGENT_PACKAGE
Set-Location .\INIS_MULTI_AGENT_PACKAGE
.\install_multi_agent_setup.ps1 -RepoPath "C:\Users\LATITUDE 5420\Downloads\INIS"
```

Puis :

```powershell
Set-Location "C:\Users\LATITUDE 5420\Downloads\INIS"
.\scripts\bootstrap_agent_worktrees.ps1
```

Enfin, vérifie :

```powershell
git status
git worktree list
```

Les agents développent dans leurs worktrees dédiés et poussent leurs branches. Les PR sont ensuite validées par GitHub Actions avant intégration.
