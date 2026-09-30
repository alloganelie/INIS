# Les 8 Invariants Fondamentaux d'INIS (§0.2)

Ces invariants sont vérifiés automatiquement par `scripts/check_invariants.py`.

1. **Aucune affirmation sans source** : tout fait émis par le système doit être rattaché à une source `SRC_{ULID}` existante.
2. **Zéro hallucination non qualifiée** : une déduction ou extrapolation sans preuve formelle est taguée obligatoirement comme `hypothesis` dans les `assumptions`.
3. **Séparation RAW / NORMALIZED / ENRICHED / DERIVED** : chaque unité porte son statut de cycle de vie immuable.
4. **Auditabilité complète** : toute transformation produit un enregistrement de lignage `TRF_{ULID}` et un événement d'audit `AUD_{ULID}`.
5. **Score de confiance explicable** : jamais un nombre magique ; toujours décomposé sur ses 7 dimensions (§15).
6. **Gestion explicite des contradictions** : les conflits entre sources sont conservés, journalisés et remontés, jamais masqués.
7. **Identifiants immuables typés ULID** : Crockford base32 avec préfixes majuscules stricts (`REQ_`, `INF_`, `SRC_`, `EVID_`...).
8. **Séparation stricte des faits et hypothèses** : dans toute livraison (§24.1), seuls les faits avec preuve avérée sont dans `findings`.

