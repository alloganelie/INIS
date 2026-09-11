# INIS — Change Requests

## Pourquoi

Une Change Request empêche un agent de modifier silencieusement le travail d'une autre zone ou un contrat partagé.

## Une CR est obligatoire si

- une interface publique doit changer ;
- un fichier hors zone doit être modifié ;
- une dépendance architecturale nouvelle est nécessaire ;
- un nom canonique doit changer ;
- une table existante doit être modifiée hors périmètre de la phase ;
- un protocole de message doit changer ;
- une règle de sécurité doit être assouplie.

## Processus

`besoin → CR → analyse d'impact → décision → implémentation → tests → fermeture`

## Priorités

- `P0` : bloque le système ou sécurité critique.
- `P1` : bloque la phase.
- `P2` : amélioration nécessaire mais non bloquante.
- `P3` : amélioration future.

## Règle

Une CR refusée ne doit pas être implémentée implicitement sous une autre forme.
