# INIS — Testing Strategy

## Niveaux

### Unit

Teste une fonction, une classe ou un module isolé.

### Integration

Teste plusieurs couches ensemble : PostgreSQL, RabbitMQ, stockage objet, API, etc.

### Contract

Vérifie qu'un producteur et un consommateur respectent la même interface.

### Agentic

Teste les comportements d'un agent : compréhension, planification, sélection d'outils, reprise, délégation et arrêt.

### Non-hallucination

Vérifie qu'une sortie factuelle ne contient pas de fait non traçable lorsque la règle de provenance l'exige.

## Porte minimale avant merge

- tests unitaires de la zone ;
- tests contractuels concernés ;
- tests d'intégration concernés.

## Porte avant clôture de phase

- suite complète disponible ;
- démarrage Docker ;
- migrations ;
- flux critiques ;
- tests de régression.

## Échec

Un test échoué n'est pas à masquer. L'agent doit identifier la cause, corriger ou créer une CR si le problème relève d'une autre zone.
