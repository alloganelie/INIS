# INIS — Intelligent Networked Information System

> **INIS v1.0.0** — Agent d'information autonome et pair-à-pair conforme à `INIS_SPEC.md` v0.2.0.

[![Architecture Checks](https://img.shields.io/badge/Architecture-100%25%20OK-brightgreen)]()
[![Contracts Checks](https://img.shields.io/badge/Contracts-100%25%20OK-brightgreen)]()
[![Tests](https://img.shields.io/badge/Tests-566%20passed-brightgreen)]()
[![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.12-blue)]()

---

## 1. Vue d'ensemble

INIS est un système d'agents d'information autonomes capables d'extraire, d'analyser, de croiser et de livrer de l'information sourcée et vérifiée.

### Invariants fondamentaux (§0.2)
- **Jamais d'affirmation sans source** : tout fait émis doit être traçable à un `RawSource`.
- **Zéro hallucination non qualifiée** : toute déduction sans preuve formelle est taguée comme hypothèse.
- **Identifiants immuables ULID** : Crockford 26 chars avec préfixe typé (`REQ_`, `INF_`, `SRC_`, `TRF_`, `PKG_`...).
- **Auditabilité complète** : toute transformation est journalisée dans la chaîne de traçabilité (`LineageTracker`).

---

## 2. Installation rapide

### Pré-requis
- Python 3.11+
- Virtualenv activé

```bash
git clone https://github.com/alloganelie/INIS.git
cd inis
python -m venv .venv
source .venv/bin/activate  # ou .venv\Scripts\activate sous Windows
pip install -e .
```

### Lancer la suite de vérification
```bash
python scripts/check_architecture.py
python scripts/check_contracts.py
python -m pytest -q
```

---

## 3. Démarrage de l'application

```bash
# Lancement de l'API FastAPI
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Endpoints principaux disponibles :
- Documentation OpenAPI : `http://localhost:8000/docs`
- Health check liveness : `GET /health` ou `GET /v1/health`
- Readiness probes : `GET /v1/health/ready`
- Information Requests : `POST /v1/requests`
- SSE Event stream : `GET /v1/requests/{id}/events`

---

## 4. Architecture

Consultez `ARCHITECTURE.md` pour le plan détaillé des modules et `CONTRACTS.md` pour les contrats inter-composants.

```
app/
├── core/            # Configuration, erreurs, primitives d'hachage
├── domain/          # Entités, value objects, interfaces (aucun I/O)
├── agents/          # Compréhension, planification, runtime
├── connectors/      # Connecteurs de sources (Web, DB, Fichiers, API)
├── storage/         # Persistance PostgreSQL, pgvector, S3/MinIO
├── messaging/       # Protocoles AMQP/MQTT, enveloppes inter-agents
├── quality/         # Règles de qualité et scores explicables (§13)
├── confidence/      # Modèle d'évaluation de confiance bayésien (§15)
├── provenance/      # Graphe de lignage et traçabilité (§14)
├── governance/      # Audit, conformité, rétention de données (§18)
├── security/        # Authn, Authz (ABAC/RBAC), détection PII (§19)
├── llm/             # Routeur de modèles, tâches, observabilité
├── workers/         # Consommateurs asynchrones d'arrière-plan
└── api/             # API HTTP FastAPI v1 (§32)
```

---

## 5. Tests et Qualité

La suite comprend **566 tests unitaires et d'intégration** :
- `tests/unit/` : tests unitaires rapides et isolés sans dépendance externe.
- `tests/integration/` : tests de conformité aux contrats de phases et validation de bout-en-bout.
- `tests/api/` : tests des endpoints REST et middleware d'authentification.

