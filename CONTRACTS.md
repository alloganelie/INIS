# INIS — Contracts

Ce document définit la règle de gestion des interfaces. Les définitions détaillées des objets restent dans l'architecture et les fichiers de code correspondants ; ce document empêche les agents de les réinventer.

## 1. Hiérarchie des sources de vérité

1. Contrat explicitement validé.
2. Architecture INIS.
3. Code existant validé par les tests.
4. Documentation de zone.
5. Hypothèse d'un agent — jamais suffisante pour modifier un contrat.

## 2. Contrats fondamentaux

Les concepts suivants doivent avoir un nom, une structure et une sémantique cohérents partout :

- `InformationRequest`
- `InformationPackage`
- `InformationUnit`
- `Evidence`
- `Source`
- `Document`
- `Dataset`
- `Claim`
- `Conflict`
- `Artifact`
- `Envelope`
- `AgentIdentity`
- `Plan`
- `PlanStep`
- `Execution`

## 3. InformationPackage

`InformationPackage` est le conteneur canonique d'information destiné à la livraison inter-agent.

Il ne constitue pas une synthèse métier arbitraire. Il transporte des informations, preuves, provenance, sources, artefacts, limitations et conflits selon le contrat validé.

## 4. Envelope

Tous les messages inter-agents doivent respecter le contrat d'enveloppe du protocole. Les agents ne doivent pas créer une enveloppe parallèle.

Les champs de traçabilité tels que `message_id`, `correlation_id`, `causation_id` et `trace_id` doivent conserver leur signification.

## 5. Compatibilité

Une modification d'un champ public doit être classée :

- additive non breaking ;
- breaking ;
- deprecated ;
- migration required.

Toute modification breaking nécessite une Change Request et une validation d'intégration.

## 6. Règle pour les agents

Si un agent ne trouve pas un contrat nécessaire :

- il ne l'invente pas ;
- il ne modifie pas silencieusement un contrat existant ;
- il crée une Change Request.
