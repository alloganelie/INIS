# INIS — Git Workflow

## 1. Branches

Branches principales :

- `main` : état validé.
- `phase/<nn>-<name>` : intégration de la phase en cours.
- `agent/<agent>-<zone>` : travail d'un agent.
- `fix/<name>` : correction ciblée après intégration.

## 2. Règle

Un agent ne pousse pas directement dans `main`.

Le travail suit :

`agent branch → phase branch → tests → main`

## 3. Commits

Utiliser des commits petits et cohérents.

Format recommandé :

`type(scope): description`

Exemples :

- `feat(domain): add information package`
- `feat(storage): persist information packages`
- `fix(messaging): handle duplicate message`
- `test(storage): cover package repository`
- `docs(contracts): define package delivery`

## 4. Pull Request

Une PR doit préciser :

- objectif ;
- zone ;
- fichiers touchés ;
- contrat concerné ;
- tests ;
- migration éventuelle ;
- risque de régression.

## 5. Merge

Pas de merge si :

- tests obligatoires rouges ;
- contrat non documenté ;
- migration incohérente ;
- fichier hors propriété modifié sans autorisation ;
- secrets ajoutés au dépôt.

## 6. Conflits Git

Ne pas résoudre un conflit en choisissant automatiquement "ours" ou "theirs". Lire le contrat et les deux modifications, puis préserver le comportement correct.

## 7. Tags de phase

À la validation complète d'une phase, créer un tag du type :

`phase-01-complete`

Le tag doit correspondre à un commit testé.
