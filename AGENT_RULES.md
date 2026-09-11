# INIS — Agent Rules

Ces règles sont obligatoires pour Codex, Devin, Antigravity, Cursor, OpenCode et tout nouvel agent de coding.

## 1. Avant de coder

L'agent doit lire :

1. l'architecture INIS ;
2. `CODING_RULES.md` ;
3. `NAMING.md` ;
4. `CONTRACTS.md` ;
5. `DEPENDENCY_RULES.md` ;
6. le README de sa zone ;
7. les fichiers directement importés par les fichiers qu'il modifie.

## 2. Propriété de zone

Chaque agent possède une zone de travail explicite.

- `OWNED` : modification autorisée.
- `READ_ONLY` : lecture autorisée, modification interdite.
- `FORBIDDEN` : ne pas modifier ni dépendre directement.

## 3. Modification hors zone

Si une modification hors zone est nécessaire :

1. arrêter la modification ;
2. créer une Change Request ;
3. décrire le besoin et l'impact ;
4. attendre la décision de l'intégrateur.

## 4. Pas de refactor opportuniste

Ne pas refactorer des fichiers non nécessaires à la tâche. Ne pas renommer une série de fichiers simplement parce qu'un autre nom semble préférable.

## 5. Pas de réécriture globale

Ne jamais régénérer ou réécrire une zone entière pour une petite fonctionnalité.

## 6. Dépendances

Avant d'ajouter une dépendance : vérifier qu'elle n'existe pas déjà et qu'elle respecte `DEPENDENCY_RULES.md`.

## 7. Tests

L'agent doit tester les fichiers qu'il modifie et fournir le résultat exact des tests.

## 8. Rapport obligatoire

Toute livraison doit indiquer :

- fichiers créés ;
- fichiers modifiés ;
- fichiers supprimés ;
- interfaces publiques changées ;
- nouvelles dépendances ;
- migrations ;
- tests exécutés ;
- problèmes restants.

## 9. Interdiction d'invention

Si une information manque, l'agent doit demander ou créer une Change Request. Il ne doit pas inventer un contrat, un comportement métier ou une source de vérité.
