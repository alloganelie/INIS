# INIS — Phase Workflow

## 1. Préparation

Avant chaque phase :

1. définir le périmètre ;
2. geler les contrats nécessaires ;
3. attribuer les zones ;
4. attribuer les agents ;
5. définir les tests d'acceptation ;
6. créer la branche de phase.

## 2. Développement parallèle

Chaque agent travaille uniquement dans sa zone.

Les dépendances entre zones sont satisfaites via les contrats, pas par modification sauvage des fichiers des autres agents.

## 3. Intégration

L'intégrateur fusionne les branches une par une et exécute les tests après chaque groupe logique de merges.

## 4. Test local réel

Après intégration :

- démarrer Docker ;
- exécuter migrations ;
- démarrer les services ;
- exécuter tests unitaires ;
- exécuter tests d'intégration ;
- exécuter tests agentiques lorsque concernés ;
- tester les flux réels critiques.

## 5. Validation humaine

Le propriétaire du projet exécute le système et valide le comportement observable.

## 6. Correction

Les corrections restent sur la branche de phase jusqu'à validation.

## 7. Clôture

Une phase est terminée uniquement lorsque `DEFINITION_OF_DONE.md` est respecté.

Créer ensuite le tag de phase et ouvrir la phase suivante à partir de cet état stable.
