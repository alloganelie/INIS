# INIS — Security Rules

## 1. Secrets

Aucun secret dans le code ou Git :

- API keys ;
- JWT secrets ;
- passwords ;
- tokens ;
- certificats privés.

Utiliser les mécanismes de configuration/secrets prévus.

## 2. Logs

Ne jamais logger :

- mots de passe ;
- tokens complets ;
- clés API ;
- données personnelles non nécessaires ;
- contenu sensible sans justification.

## 3. Entrées externes

Toute entrée externe doit être validée à la frontière appropriée.

## 4. Autorisation

Ne pas contourner RBAC/ABAC pour simplifier un développement.

## 5. Suppression

La suppression physique n'est pas un raccourci de développement. Respecter la règle de suppression logique et la gouvernance définies par l'architecture.

## 6. Dépendances

Les dépendances doivent être vérifiées avant intégration. Les versions doivent être reproductibles autant que possible.

## 7. Sécurité et agents

Un agent de coding ne doit jamais désactiver une protection simplement pour faire passer un test. Si une protection bloque le fonctionnement attendu, créer une Change Request.
