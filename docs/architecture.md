# Vue d'Ensemble de l'Architecture INIS

## 1. Principes et Couches
INIS est structuré en couches strictes sans dépendances cycliques (contrôlé par `scripts/check_architecture.py`) :
- **`app/core`** : Primitives de base, version, statuts canoniques, hashing, logging.
- **`app/domain`** : Entités pures, objets-valeurs, contrats métier sans E/S.
- **`app/agents`** : Compréhension, planification, exécution des étapes.
- **`app/connectors`** : Interfaces vers les sources (Web, PostgreSQL, S3, PDF...).
- **`app/storage`** : Repositories, base de données PostgreSQL, cache Valkey, recherche sémantique.
- **`app/confidence`** : Modèle d'évaluation de confiance explicable à 7 dimensions (§15).
- **`app/governance`** : Audit, contrôle budgétaire, politiques d'accès.
- **`app/llm`** : Routeur de modèles, tâches spécialisées, traces décisionnelles.
- **`app/messaging`** : Protocoles de communication inter-agents (AMQP/MQTT).
- **`app/observability`** : Registre des 14 métriques §34, sondes de santé.
- **`app/api`** : Interface HTTP FastAPI v1.

Consultez le document racine `ARCHITECTURE.md` pour l'arborescence complète et détaillée.

