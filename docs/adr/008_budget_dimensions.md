# ADR 008 : Dimensions de Budget Multiples et Contrôle Hard (§41.2)

## Contexte et Problématique
Une contrainte budgétaire exprimée uniquement en coût monétaire est insuffisante pour maîtriser la consommation de ressources distinctes (tokens, appels réseau, temps CPU).

## Décision
Adopter les 7 dimensions d'imputation et de contrôle de quota (§41.2) :
1. `tokens_llm_input`
2. `tokens_llm_output`
3. `web_requests`
4. `api_calls`
5. `storage_bytes_written`
6. `storage_bytes_read`
7. `compute_seconds`

Tout dépassement d'un plafond configuré déclenche l'arrêt immédiat avec le statut normatif `BUDGET_EXCEEDED` et produit un `usage_report` détaillé.

