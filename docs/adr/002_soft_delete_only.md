# ADR 002 : Rétention et Soft Delete Obligatoire (§0.2, §18)

## Contexte et Problématique
Dans un système d'intelligence auditable et décisionnel, la perte définitive ou non tracée de données entraîne la rupture de la chaîne de preuve (§0.2 invariant 4).

## Décision
- Interdire toute suppression physique (`DELETE` SQL) directe sur les entités maîtresses (`sources`, `information_units`, `evidence`, `audit_events`, `transformations`).
- Implémenter le **Soft Delete** : horodatage `deleted_at` et statut `archived`/`deleted`.
- Les requêtes de lecture courantes filtrent par défaut sur les enregistrements actifs, mais la chaîne de lignage peut toujours remonter jusqu'à la source historique.

## Conséquences
- **Auditabilité** garantie : aucune rupture de graphe de provenance.
- Nécessité d'une politique de rétention explicite et de partitionnement pour maîtriser la volumétrie sur le long terme.

