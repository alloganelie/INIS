# Modèle de Confiance Explicable à 7 Dimensions (§15)

## 1. Principe Fondamental (§15.3)
Le score de confiance d'INIS n'est **explicitement pas une probabilité** (`not_a_probability: True`).
Il s'agit d'une somme pondérée et déterministe sur 7 dimensions évaluées entre 0.0 et 1.0.

## 2. Formule et Poids Canoniques (§15.2)
```text
confidence_score =
    0.20 * source_reliability +
    0.10 * source_freshness +
    0.15 * extraction_confidence +
    0.15 * data_quality +
    0.15 * evidence_strength +
    0.15 * cross_source_agreement +
    0.10 * methodological_consistency
```
La somme des poids est exactement égale à 1.0.

## 3. Les 7 Dimensions (§15.1)
1. **`source_reliability` (0.20)** : Fiabilité intrinsèque des sources consultées.
2. **`source_freshness` (0.10)** : Décroissance temporelle par rapport à l'âge des informations.
3. **`extraction_confidence` (0.15)** : Certitude liée à la méthode d'extraction (page complète vs snippet).
4. **`data_quality` (0.15)** : Conformité aux contrôles qualité de données (§13).
5. **`evidence_strength` (0.15)** : Force probante des citations et extraits collectés.
6. **`cross_source_agreement` (0.15)** : Degré de concordance entre sources distinctes.
7. **`methodological_consistency` (0.10)** : Traçabilité et complétude de la chaîne de provenance.

