# INIS — Dependency Rules

## 1. Principe

Les dépendances doivent suivre les frontières de l'architecture.

## 2. Domain

`app/domain/` ne dépend pas directement de :

- SQLAlchemy ;
- httpx ;
- PostgreSQL ;
- Redis ;
- RabbitMQ ;
- FastAPI ;
- fichiers locaux ;
- réseau ;
- fournisseurs LLM.

## 3. Storage

`app/storage/` implémente la persistance et peut utiliser les bibliothèques de persistence prévues.

Les repositories sont responsables du SQL selon l'architecture.

## 4. Connectors

Les connectors implémentent les accès techniques aux sources. Ils ne doivent pas devenir une couche d'analyse métier.

## 5. API

L'API dépend des couches applicatives prévues ; elle ne doit pas accéder directement aux tables SQL.

## 6. Frontend

Le frontend dépend de l'API, pas de la base de données.

## 7. Ajout d'une bibliothèque

Avant toute nouvelle dépendance :

1. vérifier si une bibliothèque existante couvre le besoin ;
2. vérifier licence et maintenance ;
3. évaluer impact image Docker ;
4. ajouter la dépendance au bon manifeste ;
5. tester l'installation propre.
