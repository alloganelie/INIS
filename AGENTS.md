# AGENTS.md — Guide pour les agents IA sur INIS

Fichier lu automatiquement par les agents (Codex, Cursor, OpenCode…).

## 🚫 Règles absolues

1. Ne modifie QUE les dossiers assignés à ton rôle (`AGENT_ASSIGNMENTS.md`)
2. NE LIS JAMAIS `INIS_SPEC.md` en entier — utilise l'index ci-dessous
3. Ne committe JAMAIS de secrets (`.env`, `.pem`, clés API)
4. Lance toujours avant de committer :
   python scripts\check_architecture.py
   python scripts\check_contracts.py
   python -m pytest -q

## 📚 Documentation de référence

| Sujet | Fichier |
|---|---|
| Spécification complète | `INIS_SPEC.md` (4000 lignes — NE PAS lire en entier) |
| Arborescence | `ARCHITECTURE.md` |
| Contrats entre modules | `CONTRACTS.md` |
| Règles de code | `CODING_RULES.md` |
| Nommage | `NAMING.md` |
| Décisions d'architecture | `docs/adr/*.md` |
| Protocole multi-agent | `agent_workspace/AGENT_WORKSPACE_PROTOCOL.md` |

## 🎯 Index par rôle — Quelles sections de INIS_SPEC.md lire

### Codex — `app/core/`, `app/domain/`, `app/agents/`, `app/planning/`, `app/knowledge/`, `app/quality/`, `app/confidence/`, `app/provenance/`, `app/llm/`

- §0.2 — Invariants vérifiables ⚠️
- §0.3 — Identifiants ULID ⚠️
- §7   — Modèle de demande
- §8   — Planification autonome
- §11  — InformationUnit
- §12  — Cycle de vie RAW → DERIVED
- §13  — Qualité des données
- §14  — Preuves et contradictions
- §15  — Modèle de confiance
- §22  — LLM et Model Router
- §24  — Contrat de livraison

### Devin — `app/storage/`, `migrations/`, `app/connectors/`, `app/tools/`, `app/governance/`, `app/security/`, `app/artifacts/`, `docker/`, `deploy/`, `configs/`, `scripts/`

- §0.2, §0.3 — Invariants + Identifiants ⚠️
- §4   — Stack technique
- §9   — Connecteurs de sources
- §16  — Recherche vectorielle (pgvector)
- §18  — Gouvernance de la donnée
- §19  — Sécurité (authn, authz, PII)
- §20  — Audit et observabilité
- §27  — Modèle de données (tables)
- §41.5 — Cache et invalidation
- §41.14 — Migrations sans interruption

### OpenCode — `app/messaging/`, `app/registry/`, `app/workers/`, `app/observability/`

- §0.2, §0.3 — Invariants + Identifiants ⚠️
- §4.4 — Broker AMQP/MQTT
- §5   — Protocoles inter-agents ⚠️
- §5.1 — Envelope commune
- §5.2 — Types de messages V1
- §5.3 — Idempotence
- §6   — Agent Registry
- §20.2 — Trace distribuée
- §34  — Métriques obligatoires
- §41.8 — Retry et circuit breaker
- §41.10 — Délégation (topologie)
- §41.11 — Migration du protocole

### Antigravity — `app/api/`, `frontend/`

- §0.2 — Invariants ⚠️
- §7   — Modèle de demande
- §24  — Contrat de livraison
- §31  — Frontend minimal
- §32  — API interne/externe ⚠️
- §41.15 — OpenAPI automatique

### Cursor — Intégrateur / tests / CI

- §33  — Tests obligatoires ⚠️
- §36  — Critères d'acceptation V1
- §37  — Règle absolue de conception
- §41.13 — Tests de charge

## 📝 Convention de commit

Format : `<type>(<zone>): <description>`
Types : feat, fix, docs, test, chore, refactor
Exemples :
- `feat(domain): add InformationPackage entity per §11`
- `test(storage): cover pgvector hybrid search per §16.2`