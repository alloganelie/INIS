# Agent Status

## Dernière mise à jour
2026-09-22 — PHASE-11 Vague 1 clôturée, Vague 2 à lancer

## Commit de référence
`21ce2d9` — main

## État des phases

| Phase | Statut | Commit final | Tests | Agents |
|---|---|---|---|---|
| PHASE-01 — Socle multi-agent | ✅ | `34e6a7e` | 67 | 5 |
| PHASE-02 — Agent Runtime | ✅ | `2ca0460` | 111 | 4 |
| PHASE-03 — Transport AMQP/MQTT | ✅ | `5fb159d` | 119 | 1 (OpenCode) |
| PHASE-04 — Information Acquisition | ✅ | `1a6ac5d` | 154 | 4 + intégrateur |
| PHASE-04.2 — Corrections & Convergence | ✅ | `276e8f8` | 158 | 3 + intégrateur |
| PHASE-04.3 — Intégration réelle | ✅ | `c25e2bc` | 169 | 4 + intégrateur |
| PHASE-05 — Knowledge Layer | ✅ | `79500dd` | 209 | 4 + intégrateur |
| PHASE-05.2/05.3/05.4 — Consolidation | ✅ | `fea9262` | 238 | 4 + Codex |
| PHASE-05.5 — Nettoyage dettes | ✅ | `0533316` | 243 | 1 (Codex) |
| PHASE-06 — Quality & Confidence | ✅ | `5c0cca3` | 299 | 4 + intégrateur |
| PHASE-07 — Security | ✅ | `4ed0fa1` | 365 | 4 + intégrateur |
| PHASE-07.4 — Fix FastAPI lazy | ✅ | `d0f6fdb` | 359 | 1 (Antigravity) |
| PHASE-08 — Frontend | ✅ | `33777d5` | 374 | 4 + intégrateur |
| PHASE-09 — Orchestration E2E | ✅ | `073de81` | 415+ | 4 + intégrateur |
| PHASE-09.5 — Fix §0.2 findings vs assumptions | ✅ | `4ae9847` | 425 | 1 (Antigravity) |
| PHASE-10 — Vraie recherche web | ✅ | `1758ae5` | 452+ | 4 + intégrateur |
| PHASE-11 V1 — Comptes + Cloud + Connecteurs | ✅ | `21ce2d9` | 517 | 5 |
| PHASE-11 V2 — Résilience & protocole | 🚀 à lancer | — | — | 5 |
| PHASE-11 V3 — Gouvernance & observabilité | ⏳ | — | — | 5 |

## État des agents (par phase)

| Agent | Branche | P1 | P2 | P3 | P4 | P5 | P6 | P7 | P8 | P9 | P10 | P11-V1 | P11-V2 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Codex | agent/codex/domain | ✅ | ✅ | ⏸️ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 🚀 |
| Devin | agent/devin/storage | ✅ | ✅ | ⏸️ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 🚀 |
| OpenCode | agent/opencode/messaging | ✅ | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 🚀 |
| Antigravity | agent/antigravity/api | ✅ | ✅ | ⏸️ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 🚀 |
| Intégrateur (OpenCode) | agent/cursor/integration | ✅ | ✅ | ⏸️ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 🚀 |

## Tests
main @ `21ce2d9` : **517 passed, 2 skipped** (Docker migration 0006 + SERPER_API_KEY)

## Emplacements des worktrees

| Agent | Worktree |
|---|---|
| main | C:\Users\LATITUDE 5420\Downloads\inis |
| Codex | C:\Users\LATITUDE 5420\Downloads\INIS-worktrees\codex |
| Devin | C:\Users\LATITUDE 5420\Downloads\INIS-worktrees\devin |
| OpenCode | C:\Users\LATITUDE 5420\Documents\INIS-opencode\opencode |
| Antigravity | C:\Users\LATITUDE 5420\Downloads\INIS-worktrees\antigravity |
| Intégrateur | C:\Users\LATITUDE 5420\Downloads\INIS-worktrees\cursor |

## Dettes techniques ouvertes

**Aucune bloquante.**

### Observations mineures (PHASE-11 V2+)
1. **2 skips** : Docker (migration 0006 non testée en CI), SERPER_API_KEY (recherche réelle non exécutée en CI)
2. **mTLS validator stub** — validation de certificat reportée
3. **test_pipeline_runner_imports** — chercher au mauvais endroit (cosmétique, PHASE-09 dette)
4. **PostgresConnector** — quelques méthodes encore stub
5. **Rate limiting** — non persisté (in-memory)

### Résolues en PHASE-11 V1
- ✅ Comptes utilisateurs persistés (AccountRepository + migration 0006)
- ✅ Cloud configs réelles (K8s + Helm + docker-compose prod)
- ✅ Connecteurs XML, DOCX, RSS, PDF câblés et testés
- ✅ Password hashing PBKDF2-HMAC-SHA256
- ✅ S3/MinIO client réel (boto3)

## Exceptions documentées

- **PHASE-02** : Codex a couvert `app/registry/` + `app/workers/` (zone OpenCode).
- **PHASE-04** : OpenCode a couvert `app/connectors/api/` + `web/` (zone Devin).
- **PHASE-05.3 → 05.4** : Codex a couvert `migrations/` + `app/connectors/database/`.
- **PHASE-05.5** : Codex a couvert 6 zones pour solder les dettes.
- **PHASE-06** : OpenCode a couvert `app/confidence/` (zone Codex).
- **PHASE-07** : OpenCode a couvert `app/governance/retention/` + `lifecycle/`.
- **PHASE-07.4** : Antigravity a modifié `app/main.py` pour FastAPI 0.141.
- **PHASE-08** : Codex (types) + OpenCode (mocks) ont couvert `frontend/`.
- **PHASE-09** : Codex a fixé `test_frontend_buildable` (zone Cursor).
- **PHASE-09.5** : Antigravity a fixé `pipeline_runner.py` (§0.2).
- **PHASE-10** : aucune exception (zones respectées).
- **PHASE-11 V1** : Devin a ajouté `boto3` à `pyproject.toml` (S3 obligatoire).
- **PHASE-11 V1** : OpenCode a ajouté `python-docx`, `pypdf`, `pdfplumber`, `lxml` à `pyproject.toml` (CI cassé sinon).

## Règles actives

- **Règle 9** : placeholders vides — renommer/remplir, pas de doublon.
- **Règle 10** : migrations Alembic testées `upgrade head` + `downgrade base`.
- **Règle 11** (nouvelle) : toute lib utilisée par un agent DOIT être déclarée dans `pyproject.toml` avant merge — sinon CI casse.

## Configuration

- **OpenCode** : `C:\Users\LATITUDE 5420\Documents\INIS-opencode\opencode`
- **FastAPI 0.141.1** : 13 sous-routers montés individuellement
- **Dépendances clés** : paho-mqtt, trafilatura, readability-lxml, pgvector, numpy, aiosqlite, msw, boto3, python-docx, pypdf, pdfplumber, lxml
- **Env vars** : `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL_*`, `SERPER_API_KEY`, `S3_ENDPOINT`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `JWT_SECRET`
- **Frontend** : `cd frontend && npm install && npm run dev`
- **Auth** : opt-in `INIS_AUTH_ENABLED=true`

## Prochaines actions

**PHASE-11 Vague 2 — Résilience & protocole** :
- Codex : ProtocolVersion + DelegationGraph + trust graph (§41.10, §41.11)
- Devin : Cache L1/L2 + chunked processor (§41.5, §41.6)
- OpenCode : Retry + circuit breaker + credential vault (§41.4, §41.8)
- Antigravity : Resume + progress + graceful expiry + quotas (§41.1, §41.2)
- Intégrateur : E2E Wave 2

**PHASE-11 Vague 3 — Gouvernance & observabilité** :
- Codex : i18n + désinformation (§41.3, §41.7)
- Devin : Retention + GDPR (§41.9)
- OpenCode : Traces LLM + OpenAPI auto-doc (§41.12, §41.15)
- Antigravity : Blue/green + canary + backward-compat + health enrichi (§41.13, §41.14)
- Intégrateur : Tests de charge + clôture

**Hors scope PHASE-11** : OCR, audio, vidéo, streaming, exécution sandboxée.