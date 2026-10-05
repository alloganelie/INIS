# INIS — Intelligent Networked Information System

> **INIS 2.0.0** — Agent d'information autonome et pair-à-pair conforme à `INIS_SPEC.md` v0.2.0.

[![Architecture Checks](https://img.shields.io/badge/Architecture-OK-brightgreen)]()
[![Contracts Checks](https://img.shields.io/badge/Contracts-OK-brightgreen)]()
[![Invariants Checks](https://img.shields.io/badge/Invariants-OK-brightgreen)]()
[![Python](https://img.shields.io/badge/Python-3.12-blue)]()

---

## 1. Vue d'ensemble

INIS est un système d'agents d'information autonomes capables d'extraire, d'analyser, de croiser et de livrer de l'information sourcée et vérifiée.

### Invariants fondamentaux (§0.2)
- **Jamais d'affirmation sans source** : tout fait émis doit être traçable à un `RawSource`.
- **Zéro hallucination non qualifiée** : toute déduction sans preuve formelle est taguée comme hypothèse.
- **Identifiants immuables ULID** : Crockford 26 chars avec préfixe typé (`REQ_`, `INF_`, `SRC_`, `TRF_`, `PKG_`...).
- **Auditabilité complète** : toute transformation est journalisée dans la chaîne de traçabilité (`LineageTracker`).
- **Une seule horloge** : tous les instants passent par `app/core/time.py::utc_now()` (UTC, *timezone-aware*, jamais naïf).

---

## 2. Installation rapide

### Pré-requis
- Python **3.12+** (§4.1 `[V1-FIXE]` — le contrat, la CI et les images Docker sont en 3.12)
- Virtualenv activé
- Docker (pour les services locaux et les tests d'intégration)

```bash
git clone https://github.com/alloganelie/INIS.git
cd inis
python -m venv .venv
source .venv/bin/activate  # ou .venv\Scripts\activate sous Windows
pip install -e ".[dev]"
```

### Lancer la suite de vérification

```bash
python scripts/check_architecture.py          # arborescence et dépendances autorisées
python scripts/check_contracts.py             # contrats publics entre modules
python scripts/check_invariants.py            # invariants §0.2 (sources, ULID, audit)
python scripts/check_backward_compat.py migrations/versions/   # §41.14
ruff check .                                  # lint (aucune régression tolérée)
python -m pytest -q                           # suite complète
```

---

## 3. Démarrage de l'application

### Développement (services locaux)

```bash
docker compose up -d postgres valkey object-storage   # PostgreSQL+pgvector, Valkey, stockage S3
alembic upgrade head                                  # schéma (§41.14)
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Image de production (§4.3)

`uvicorn` est déclaré en **dépendance de production** : `pip install .` suffit à
servir l'API, l'image `docker/Dockerfile` démarre donc réellement (utilisateur
non-root, healthcheck `/health`).

```bash
docker build -f docker/Dockerfile -t inis:prod .
docker run --rm -p 8000:8000 \
  -e INIS_DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/inis_db \
  -e S3_ENDPOINT=http://host:9000 -e S3_ACCESS_KEY=... -e S3_SECRET_KEY=... \
  inis:prod
```

### Endpoints principaux

- Documentation OpenAPI : `http://localhost:8000/docs` (schéma : `GET /v1/openapi.json`, export `python scripts/export_openapi.py`)
- Liveness : `GET /health` ou `GET /v1/health` — Readiness : `GET /v1/health/ready`
- Observabilité (§34) : `GET /v1/metrics` (JSON ou `?format=prometheus`) — les huit seuils §41.13 sont sous `benchmarks`
- Requêtes : `POST /v1/requests` (déclenche le pipeline §28), `GET /v1/requests/{id}` (état §1.3), `GET /v1/requests/{id}/events` (SSE)
- Livraison (§24.2) : `POST /v1/requests/{id}/documents`, `GET /v1/artifacts`, `GET /v1/artifacts/{id}/download`


---

## 4. Architecture

Consultez `ARCHITECTURE.md` pour le plan détaillé des modules, `CONTRACTS.md` pour les contrats inter-composants et `docs/adr/` pour les décisions.

```
app/
├── core/            # Configuration, erreurs, hachage, limites, horloge UTC
├── domain/          # Entités, value objects, interfaces (aucun I/O)
├── agents/          # Compréhension, planification, runtime, budgets
├── connectors/      # Connecteurs de sources (§9) + registre de plugins (§9.2)
├── knowledge/       # Ingestion, normalisation, enrichissement, mémoire (§11/§16)
├── planning/        # Planification, garde-fous de plan et de concurrence (§41.13)
├── quality/         # Règles de qualité et scores explicables (§13)
├── confidence/      # Modèle d'évaluation de confiance (§15)
├── provenance/      # Graphe de lignage et traçabilité (§14)
├── governance/      # Audit, conformité, rétention, RGPD (§18)
├── security/        # Authn (mTLS), Authz (ABAC/RBAC), PII, Vault, rate limiting (§19)
├── llm/             # Routeur de modèles, tâches, traçabilité (§22, §41.12)
├── artifacts/       # Génération et livraison d'artefacts (§24.2/§24.3)
├── messaging/       # Protocoles AMQP/MQTT, enveloppes inter-agents (§5)
├── registry/        # Agent Registry (§6)
├── storage/         # PostgreSQL, pgvector, S3/MinIO, repositories
├── observability/   # Métriques §34, santé, traces
├── workers/         # Consommateurs asynchrones d'arrière-plan
└── api/             # API HTTP FastAPI v1 (§32)
frontend/            # UI minimale (React + Vite + TypeScript)
```

---

## 5. Tests et qualité

| Suite | Contenu |
|---|---|
| `tests/unit/` | unités rapides et isolées (dont `tests/unit/core/test_time.py` : horloge unique) |
| `tests/integration/` | conformité aux contrats et parcours réels (PostgreSQL, stockage objet, brokers) |
| `tests/api/` | endpoints REST, middlewares, OpenAPI |
| `tests/security/` | AuthZ, mTLS, PII, RGPD, rate limiting, hygiène des secrets |
| `tests/performance/` | dimensionnement par composant (recherche vectorielle, chunking, agents) |
| `tests/load/` | harnais de charge §41.13 (parcours réel `upload → ... → download`) |
| `tests/agentic/` | non-hallucination, traçabilité, conflits, délégation |

### Frontend

```bash
cd frontend
npm ci
npx tsc --noEmit          # typecheck
npm run build             # build Vite
npx vitest run            # tests unitaires
```

---

## 6. Charge et dimensionnement (§41.13)

Le harnais mesure le **chemin réel** (`upload → ingestion → pipeline → livraison → téléchargement`, `sha256` vérifié) et **lit** les seuils dans `GET /v1/metrics → benchmarks` (aucun chiffre inventé).

```bash
python -m tests.load.run_load --base-url http://127.0.0.1:8000 \
    --requests 5 --concurrency 2 --rows 25            # portée locale : seuils publiés, non appliqués
python -m tests.load.run_load --base-url https://staging... --scope staging   # seuils appliqués
```

Résultats archivés dans `tests/load/results/` (JSON trié). CI **manuelle** : `.github/workflows/load.yml`.

---

## 7. Extensions (§9.2)

Un connecteur externe (OCR, audio, vidéo, streaming — hors V1) s'enregistre via le
groupe d'`entry_points` **`inis.connectors`**, sans modifier le cœur. Registre :
`app/connectors/plugins.py` ; contrat : `SourceConnector` (`app/connectors/base.py`) ;
procédure : `docs/adr/010_plugin_registration.md`.

---

## 8. Sécurité (§19)

- **AuthN** : mTLS service-à-service (`app/security/certificates/`), extension ASGI standard.
- **AuthZ** : politiques ABAC/RBAC, artefacts supprimés non téléchargeables, scopes.
- **Credentials** : Vault (`app/security/vault/`) branché sur les connecteurs.
- **Rate limiting** : store partagé **Valkey** (`REDIS_URL`, protocole Redis) + repli process-local mesuré.
- **RGPD (§41.9)** : effacement, rectification, portabilité, rétention.
- **Secrets** : `gitleaks` en CI (`.github/workflows/security.yml`, `.gitleaks.toml`).

---

## 9. Documentation

| Sujet | Fichier |
|---|---|
| Spécification normative | `INIS_SPEC.md` |
| Plan de conformité et journal des lots | `docs/SPEC_CONFORMANCE_PLAN.md` |
| Couverture par section de spec | `docs/SPEC_COVERAGE.md` |
| Contrats inter-modules | `CONTRACTS.md` |
| Règles de code et nommage | `CODING_RULES.md`, `NAMING.md` |
| Déploiement, performance, API | `docs/deployment.md`, `docs/performance_tuning.md`, `docs/api_guide.md` |
| Décisions d'architecture | `docs/adr/*.md` |

