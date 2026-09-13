# INIS — Agent Rules

Ces règles sont obligatoires pour Codex, Devin, Antigravity, Cursor, OpenCode et tout nouvel agent de coding.

## 1\. Avant de coder

L'agent doit lire :

1. l'architecture INIS ;
2. `CODING\_RULES.md` ;
3. `NAMING.md` ;
4. `CONTRACTS.md` ;
5. `DEPENDENCY\_RULES.md` ;
6. le README de sa zone ;
7. les fichiers directement importés par les fichiers qu'il modifie.

## 2\. Propriété de zone

Chaque agent possède une zone de travail explicite.

* `OWNED` : modification autorisée.
* `READ\_ONLY` : lecture autorisée, modification interdite.
* `FORBIDDEN` : ne pas modifier ni dépendre directement.

## 3\. Modification hors zone

Si une modification hors zone est nécessaire :

1. arrêter la modification ;
2. créer une Change Request ;
3. décrire le besoin et l'impact ;
4. attendre la décision de l'intégrateur.

## 4\. Pas de refactor opportuniste

Ne pas refactorer des fichiers non nécessaires à la tâche. Ne pas renommer une série de fichiers simplement parce qu'un autre nom semble préférable.

## 5\. Pas de réécriture globale

Ne jamais régénérer ou réécrire une zone entière pour une petite fonctionnalité.

## 6\. Dépendances

Avant d'ajouter une dépendance : vérifier qu'elle n'existe pas déjà et qu'elle respecte `DEPENDENCY\_RULES.md`.

## 7\. Tests

L'agent doit tester les fichiers qu'il modifie et fournir le résultat exact des tests.

## 8\. Rapport obligatoire

Toute livraison doit indiquer :

* fichiers créés ;
* fichiers modifiés ;
* fichiers supprimés ;
* interfaces publiques changées ;
* nouvelles dépendances ;
* migrations ;
* tests exécutés ;
* problèmes restants.

## 9\. Interdiction d'invention

Si une information manque, l'agent doit demander ou créer une Change Request. Il ne doit pas inventer un contrat, un comportement métier ou une source de vérité.
## Règle 9 — Gestion des placeholders vides



\### Contexte



L'arborescence initiale du dépôt contient de nombreux fichiers vides (0 octet)

créés comme \*\*placeholders\*\* pour structurer le projet : migrations Alembic,

modules, classes, etc.



Ces placeholders ne reflètent pas nécessairement l'ordre réel ou le contenu

réel des implémentations qui seront faites plus tard.



\### Règle



Quand un agent doit créer un nouveau fichier qui \*\*entre en conflit\*\* avec un

placeholder vide existant (même nom, même numéro de migration, même chemin) :



1\. \*\*Ne PAS créer de doublon\*\* — jamais deux fichiers avec le même identifiant.

2\. \*\*Renommer le placeholder\*\* vers le nom qui reflète le contenu réel.

3\. \*\*Remplir le placeholder renommé\*\* avec le contenu de la mission.

4\. \*\*NE PAS conserver le placeholder vide\*\* à côté du fichier réel.



\### Justification



\- L'arborescence initiale a été conçue comme un squelette indicatif, pas comme

&#x20; un contrat figé.

\- La convention retenue est : \*\*le nom du fichier reflète son contenu réel\*\*,

&#x20; pas le placeholder d'origine.

\- Cette convention a déjà été appliquée plusieurs fois :

&#x20; - `0002\_create\_agents.py` → `0002\_create\_core\_tables.py` (PHASE-04.3)

&#x20; - `0003\_create\_requests.py` → `0003\_create\_embeddings\_and\_search.py` (PHASE-05)

&#x20; - `0004\_create\_plans.py` → `0004\_create\_transformations.py` (PHASE-05.2)



\### Exemples



\#### Cas 1 — Migration Alembic en conflit



\*\*Situation :\*\* Un agent doit créer la migration `0004\_create\_transformations.py`

mais `0004\_create\_plans.py` existe déjà (vide).



\*\*Action correcte :\*\*

\- Renommer `0004\_create\_plans.py` → `0004\_create\_transformations.py`

\- Remplir avec la migration transformations

\- La table `plans` sera créée dans une migration ultérieure quand elle sera

&#x20; réellement nécessaire



\*\*Action incorrecte :\*\*

\- Créer un nouveau fichier `0004\_create\_transformations.py` à côté de

&#x20; `0004\_create\_plans.py` → \*\*graphe Alembic ambigu\*\*



\#### Cas 2 — Module Python en conflit



\*\*Situation :\*\* Un agent doit créer `app/quality/score/quality\_scorer.py`

mais `app/quality/scorer.py` existe déjà (vide).



\*\*Action correcte :\*\*

\- Supprimer ou renommer `app/quality/scorer.py`

\- Créer `app/quality/score/quality\_scorer.py` selon la mission

\- Signaler le renommage dans le rapport final



\### En cas de doute



Si l'agent n'est pas sûr de la bonne action (renommer, déplacer, supprimer) :

\*\*demander à l'humain AVANT d'agir\*\*. Ne jamais créer de doublon silencieusement.



\### Rapport final



Tout renommage ou suppression de placeholder DOIT être listé dans le rapport

final, section « Décisions / Exceptions », avec :

\- Le nom du placeholder d'origine

\- Le nouveau nom

\- La justification

