# ADR 005 : Versioning et Tolérance du Protocole Inter-Agents (§5, §41.11)

## Contexte et Problématique
Le protocole de communication inter-agents évolue au cours du temps. Des agents tournant dans des versions différentes doivent pouvoir coopérer sans blocage brutal.

## Décision
- Versioning sémantique strict `vMAJOR.MINOR` dans l'enveloppe commune (§5.1).
- **Tolérance ascendante (§41.11)** : un agent récepteur accepte les messages d'une version mineure supérieure au sein de la même version majeure en ignorant simplement les champs non reconnus.
- **Rupture majeure** : tout écart sur la version majeure entraîne un message explicite `VALIDATION_ERROR` ou `PROTOCOL_INCOMPATIBLE` listant les versions supportées.

