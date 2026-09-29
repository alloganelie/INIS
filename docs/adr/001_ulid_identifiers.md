# ADR 001 : Identifiants immuables ULID typés (§0.3)

## Contexte et Problématique
Le système INIS orchestre de multiples agents distribués qui créent, échangent et manipulent des unités d'information, des preuves et des requêtes. Les identifiants doivent être uniques globalement, triables chronologiquement, compacts et lisibles immédiatement par un opérateur ou un agent.

## Décision
Adopter la norme **ULID** (Universally Unique Lexicographically Sortable Identifier) avec préfixes stricts typés majuscules (§0.3) :
- `REQ_{ULID}` : Requêtes d'information
- `INF_{ULID}` : Unités d'information
- `SRC_{ULID}` : Sources
- `EVID_{ULID}` : Preuves
- `PLAN_{ULID}` : Plans d'exécution
- `STEP_{ULID}` : Étapes de plan
- `AUD_{ULID}` : Événements d'audit
- `TRF_{ULID}` : Transformations
- `CONFLICT_{ULID}` : Contradictions

## Conséquences
- **Positives** : Traçabilité immédiate sans ambiguïté sur le type d'objet ; tri chronologique naturel ; compacité et sécurité URL (base32 Crockford).
- **Invariants** : Tout identifiant stocké ou transmis DOIT impérativement respecter son préfixe canonique (vérifié par `scripts/check_invariants.py`).

