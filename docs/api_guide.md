# Guide d'Utilisation de l'API INIS (§32)

## 1. Principes Généraux
L'API REST d'INIS expose la version **v1** préfixée par `/v1`.
La documentation interactive OpenAPI / Swagger est accessible sur `/v1/docs` et le schéma JSON sur `/v1/openapi.json`.

## 2. Routes Principales

### Requêtes d'information (§7, §24, §32)
- `POST /v1/requests` : Soumettre une demande d'information (asynchrone ou synchrone selon background_tasks).
- `GET /v1/requests/{id}` : Consulter l'état courant et le résultat de livraison d'une requête.
- `POST /v1/requests/{id}/cancel` : Annuler de manière coopérative et idempotente une requête en cours (`CANCELLED`).
- `GET /v1/requests/{id}/events` : Flux temps réel Server-Sent Events (SSE).
- `GET /v1/requests/{id}/usage` : Rapport de consommation des 7 dimensions budgétaires (§41.2).
- `GET /v1/requests/{id}/llm-traces` : Traces des décisions LLM anonymisées (hash SHA-256).

### Unités d'Information, Sources, Preuves & Contradictions (§9, §11, §14)
- `GET /v1/sources` & `GET /v1/sources/{id}` : Sources répertoriées avec scores de fiabilité.
- `GET /v1/information` & `GET /v1/information/{id}` : Unités d'information factuelles persistées.
- `GET /v1/evidence` & `GET /v1/evidence/{id}` : Extraits et preuves rattachés.
- `GET /v1/conflicts` & `GET /v1/conflicts/{id}` : Détections de contradictions inter-sources.

### Système et Observabilité (§20, §34, §41.15)
- `GET /health` & `GET /v1/health` : Liveness et état des composants subsystem (DB, Valkey, LLM...).
- `GET /v1/health/ready` : Readiness pour orchestrateurs de conteneurs.
- `GET /v1/metrics` : 14 métriques obligatoires §34 au format JSON ou Prometheus (`?format=prometheus`).
- `GET /v1/changelog` : Historique des révisions et migrations.

