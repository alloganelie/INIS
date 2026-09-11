# INIS — Naming Convention

## 1. Règle absolue

Un concept public = un nom canonique unique dans tout le projet.

Ne pas alterner entre `package_id`, `packageId`, `pkg_id` et `information_package_id` pour désigner le même identifiant.

## 2. Python

| Élément | Convention | Exemple |
|---|---|---|
| fichier | snake_case | `information_package.py` |
| classe | PascalCase | `InformationPackage` |
| fonction | snake_case | `build_package()` |
| variable | snake_case | `package_id` |
| constante | UPPER_SNAKE_CASE | `MAX_RETRY_COUNT` |
| module | snake_case | `source_repository` |

## 3. TypeScript

| Élément | Convention | Exemple |
|---|---|---|
| fichier logique | camelCase | `requestClient.ts` |
| composant | PascalCase | `RequestStatus.tsx` |
| type/interface | PascalCase | `InformationPackage` |
| variable | camelCase | `packageId` |
| constante | UPPER_SNAKE_CASE | `MAX_RETRIES` |

Le backend reste canonique pour les noms de champs API. Le mapping frontend doit être explicite s'il est réellement nécessaire.

## 4. Identifiants INIS

Les identifiants suivent les préfixes définis par l'architecture et les contrats. Ne pas créer un nouveau préfixe sans modification de contrat.

Exemples canoniques :

- `agent_id`
- `request_id`
- `message_id`
- `correlation_id`
- `causation_id`
- `trace_id`
- `span_id`
- `source_id`
- `document_id`
- `dataset_id`
- `information_id`
- `evidence_id`
- `claim_id`
- `conflict_id`
- `artifact_id`
- `package_id`

## 5. Fichiers courts mais explicites

Préférer `information_package.py` à `information_package_manager_service_impl.py`.

Un nom doit être court sans devenir ambigu.

## 6. Évolution des noms

Si un nom public doit changer :

1. créer une Change Request ;
2. identifier tous les consommateurs ;
3. définir une stratégie de migration ;
4. modifier le contrat ;
5. adapter les consommateurs ;
6. tester ;
7. documenter le changement.
