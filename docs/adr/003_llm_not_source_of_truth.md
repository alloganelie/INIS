# ADR 003 : Le LLM n'est jamais la source de vérité (§0.2, §22)

## Contexte et Problématique
Les grands modèles de langage (LLM) sont sujets à des hallucinations et des dérives temporelles. L'intégrité factuelle d'un système de renseignement ne peut reposer sur la mémoire paramétrique d'un modèle génératif.

## Décision
- **Invariant absolu §0.2 (Invariants 1 et 2)** : Le LLM sert exclusivement d'outil d'analyse, d'extraction, de mise en forme et de reformulation.
- Tout fait (`finding`) DOIT être sourcé explicitement avec un identifiant de source `SRC_` valide et un identifiant de preuve `EVID_`.
- Toute affirmation générée sans preuve directe DOIT être déclassée au statut épistémique d'**hypothèse** (`hypothesis`) et placée dans `assumptions`, jamais livrée comme fait établi.
- En cas d'indisponibilité ou de réponse stub d'un modèle, le pipeline dégrade explicitement et ne présente jamais une réponse fictive comme information vérifiée.

