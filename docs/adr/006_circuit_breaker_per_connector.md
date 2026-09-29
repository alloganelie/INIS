# ADR 006 : Circuit Breakers Dédiés par Connecteur et Fournisseur (§41.8)

## Contexte et Problématique
Les pannes ou blocages des fournisseurs externes (moteurs de recherche web, API tierces, LLM) ne doivent pas provoquer d'effet domino ni paralyser l'ensemble de l'orchestrateur.

## Décision
- Instancier un **Circuit Breaker** dédié par connecteur et par périmètre fournisseur (`scope="provider:..."`).
- États : `CLOSED` (nominal), `OPEN` (bloqué après seuil d'échecs consécutifs), `HALF_OPEN` (test de reprise après cooldown).
- L'ouverture d'un coupe-circuit bascule immédiatement la tâche sur le mécanisme de dégradation ou de repli (ex. fallback Wikipedia si Serper est en panne).

