# Protocole local

## Un agent = un worktree

| Agent | Worktree | Zone |
|---|---|---|
| Codex | `../INIS-worktrees/codex` | core/domain/agents/planning/knowledge/quality/confidence/provenance/llm |
| Devin | `../INIS-worktrees/devin` | storage/migrations/connectors/tools/governance/security/artifacts/docker/deploy/configs/scripts |
| OpenCode | `../INIS-worktrees/opencode` | messaging/registry/workers/observability |
| Antigravity | `../INIS-worktrees/antigravity` | api/frontend |
| Cursor | `../INIS-worktrees/cursor` | review/intégration/corrections ciblées |

Deux applications ne doivent pas éditer simultanément le même worktree.

Avant de coder, l'agent lit la gouvernance, la phase active et vérifie `git status`.

À la fin : tests, commit, push, puis handoff avec fichiers, contrats, migrations, tests, risques et commit SHA.
