# ADR 004 : Pondération de la Recherche Hybride Vectorielle et Lexicale (§16.2)

## Contexte et Problématique
La recherche purement sémantique (dense embeddings) capture le sens global mais échoue souvent sur les entités nommées rares, les numéros ou les codes spécifiques. À l'inverse, la recherche lexicale (BM25/tsvector) capture le mot exact sans comprendre les synonymes.

## Décision
Adopter une formule de fusion hybride canonique (§16.2) :
```
score_final = 0.6 * score_vectoriel + 0.4 * score_lexical
```
- Stockage dense : PostgreSQL `pgvector` avec index HNSW cosinus (1536 dimensions).
- Stockage lexical : PostgreSQL `tsvector` (`information_units.search_vector`) avec index GIN.
- Normalisation : chaque sous-score est ramené dans l'intervalle [0, 1] avant pondération.

## Conséquences
- Découvrabilité optimale combinant sens général et précision lexicale stricte.
- Respect strict des tests d'intégration et benchmarks vérifiant la formule au chiffre près.

