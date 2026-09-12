# PHASE-01 — Résumé factuel

Phase active (`agent_workspace/CURRENT_PHASE.md`) : **Stabilisation et intégration du socle multi-agent**.

Point d’intégration Cursor : branche `agent/cursor/integration`, commit de départ `9069a0c` (`Merge pull request #3 from alloganelie/agent/opencode/messaging`).

## Zones couvertes dans le dépôt à `9069a0c`

Observé dans l’arbre `app/` (fichiers Python présents) :

| Zone | Contenu présent |
|---|---|
| `app/core/` | `constants.py` (préfixes ULID, `DATA_STAGES`), `errors.py` |
| `app/domain/` | `ULID`, entité `InformationPackage` |
| `app/storage/` | `Base`, `TimestampMixin`, `SoftDeleteMixin`, engine et session async |
| `app/messaging/` | `EnvelopeBuilder`, validateur d’enveloppe, `IdempotencyGuard` |

Absents de l’arbre à ce commit (non inventés comme livrés) :

- `app/main.py` (lot API Antigravity encore en cours)
- `app/api/`, `frontend/`
- `app/agents/`, `app/planning/`, `app/knowledge/`, `app/quality/`, `app/confidence/`, `app/provenance/`, `app/llm/`
- `app/connectors/`, `app/tools/`, `app/governance/`, `app/security/`, `app/artifacts/`
- `app/registry/`, `app/workers/`, `app/observability/`

Gouvernance et outillage déjà à la racine : spec, contrats, règles agents, `scripts/check_architecture.py`, `scripts/check_contracts.py`, `pyproject.toml` (pytest, ruff, mypy).

## Tests présents avant le lot d’intégration Cursor

Unitaires (`tests/unit/`) :

- `tests/unit/core/test_ulid.py`
- `tests/unit/domain/test_information_package.py`
- `tests/unit/storage/test_base.py`
- `tests/unit/messaging/test_envelope_builder.py`
- `tests/unit/messaging/test_envelope_validator.py`
- `tests/unit/messaging/test_idempotency_guard.py`

Couverture §33 à ce stade : fumée unitaire sur ULID, `InformationPackage` (provenance), bases SQLAlchemy, protocole Envelope. Les tests d’intégration §33.2 (PostgreSQL, pgvector, object storage, RabbitMQ, MQTT, connecteurs, agent registry) ne sont pas encore livrés — ce lot n’ajoute que des smokes d’import et de coexistence d’objets, sans infrastructure.

Critères d’acceptation V1 (§36, 20 points) : aucun n’est revendiqué comme atteint par ce résumé ; le socle ULID / Envelope / InformationPackage / storage de base est en place, pas le produit V1.

## Commits jusqu’à `9069a0c` (historique `git log`)

| Commit | Message |
|---|---|
| `9069a0c` | Merge pull request #3 from alloganelie/agent/opencode/messaging |
| `7339e26` | Merge remote-tracking branch 'origin/main' into agent/opencode/messaging |
| `e07e09c` | Merge pull request #2 from alloganelie/agent/devin/storage |
| `5ecee6f` | feat(messaging): add EnvelopeBuilder, EnvelopeValidator and IdempotencyGuard per §5.1, §5.2, §5.3 |
| `9fd7ccc` | feat(storage): add SQLAlchemy base, mixins, engine, session and first migration per §4.2, §27 |
| `4ceb532` | Merge pull request #1 from alloganelie/agent/codex/domain |
| `dd01fb6` | Merge remote-tracking branch 'origin/main' into agent/codex/domain |
| `fda4d55` | fix(ci): remove trailing dot in pip install command |
| `4f27f20` | Merge remote-tracking branch 'origin/main' into agent/codex/domain |
| `1ae177e` | fix(deps): require pytest-asyncio>=0.24, install dev deps in CI |
| `9274095` | Merge remote-tracking branch 'origin/main' into agent/codex/domain |
| `b490240` | ci: disable Docker workflow for PHASE-01 (to reactivate in PHASE-04) |
| `8b39a95` | fix(build): lower requires-python to 3.11 for local compatibility |
| `5bd35b8` | Merge remote-tracking branch 'origin/main' into agent/codex/domain |
| `48bea35` | fix(scripts): update check_contracts to reflect governance docs moved to repo root |
| `f05b232` | feat(domain): add ULID, core errors and InformationPackage per §0.2, §0.3, §11 |
| `09bf574` | docs: complete AGENTS.md with full index per agent role |
| `aeeaf77` | chore: add AGENTS.md index and pyproject.toml with pytest/ruff/mypy setup |
| `ca3b3ef` | chore: add .gitignore for Python + Node project |
| `855adb3` | chore: reorganize governance docs to repo root + install multi-agent workflow |
| `a932296` | chore: initialize INIS architecture and governance |

PRs fusionnées visibles dans cet historique : #1 domain (Codex), #2 storage (Devin), #3 messaging (OpenCode).

Gate PHASE-01 documentée (non ré-évaluée ici) : worktrees, gouvernance lisible, contrats gelés, checks d’architecture, CI GitHub, tests non dégradés, pas de secret commité, intégration par PR.
