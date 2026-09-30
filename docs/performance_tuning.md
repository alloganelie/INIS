# Optimisation et Réglages de Performance INIS (§41.13)

## 1. Seuils et Limites de Charge
- `MAX_PLAN_STEPS` (défaut : 50) : Nombre maximal d'étapes qu'un planificateur peut exécuter par requête.
- `MAX_PARALLEL_TOOL_CALLS` (défaut : 10) : Concurrence maximale d'appels d'outils simultanés via `ConcurrencyLimiter`.

## 2. Niveaux de Cache (§41.5)
- **L1 (In-Memory)** : Cache mémoire local par processus (requêtes web, pages extraites).
- **L2 (Redis)** : Cache distribué inter-processus et rate limiting.
- **L3 (Vectoriel)** : Déduplication sémantique via pgvector.

## 3. Indexation Base de Données
- Index HNSW sur la table `embeddings` (distance cosinus).
- Index GIN sur `information_units.search_vector` pour la recherche lexicale rapide.

