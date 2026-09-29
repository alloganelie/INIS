# ADR 007 : Seuil de Découpage Chunking Obligatoire (§11, §21)

## Contexte et Problématique
Le traitement de documents volumineux ou de grands jeux de données dépasse les fenêtres de contexte des modèles et provoque une saturation mémoire.

## Décision
- Définir un seuil strict `max_information_units_per_request` (défaut : 50).
- Au-delà de ce seuil, le découpage en tronçons (**chunking**) devient obligatoire avant tout passage en analyse ou extraction.
- Chaque fragment conserve son lignage d'origine via les métadonnées de fragment (`document_fragment`).

