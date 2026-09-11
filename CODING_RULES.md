# INIS — Coding Rules

## 1. Principes obligatoires

1. La lisibilité prime sur la brièveté.
2. Une responsabilité principale par fichier.
3. Ne pas créer de duplication lorsqu'une abstraction existante convient.
4. Ne pas introduire de logique métier dans une couche qui ne la possède pas.
5. Ne pas créer de fichiers `TODO`, `pass`, stubs ou faux services uniquement pour satisfaire l'arborescence.
6. Toute fonctionnalité livrée doit être exécutable et testée.
7. Toute modification doit respecter les contrats existants.
8. Ne jamais inventer une interface, un champ ou un nom déjà défini ailleurs.
9. Les erreurs doivent être explicites et traçables.
10. Les opérations critiques doivent être idempotentes lorsqu'elles peuvent être rejouées.

## 2. Python

- Python 3.12+.
- Type hints sur les fonctions publiques et les structures importantes.
- Pydantic pour les contrats de données lorsque prévu par l'architecture.
- SQLAlchemy uniquement dans `storage`.
- Aucun I/O dans `domain`.
- Aucun appel HTTP direct dans `domain`.
- Pas de SQL dispersé hors repositories/migrations conformément à l'architecture.
- Exceptions métier explicites ; ne pas masquer les exceptions avec `except Exception: pass`.
- Utiliser async uniquement lorsque la couche et la dépendance sont conçues pour l'asynchrone.

## 3. Frontend

- TypeScript strict.
- `.tsx` pour composants React, `.ts` pour logique non JSX.
- Les types API doivent rester alignés avec les schémas backend.
- Aucun accès direct à PostgreSQL depuis le frontend.
- Les appels backend passent par le client API prévu.

## 4. Documentation du code

Documenter le pourquoi lorsqu'il n'est pas évident. Ne pas écrire des commentaires qui répètent simplement le code.

## 5. Modification minimale

Avant de modifier un fichier existant, l'agent doit vérifier qu'une création de fichier ou une extension locale ne permet pas d'éviter la modification.

Un fichier appartenant à une autre zone est en lecture seule sauf changement explicitement approuvé.
