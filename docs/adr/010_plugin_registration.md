# ADR 010 : Enregistrement des connecteurs externes (§9.2)

- **Statut** : accepté, **mis en œuvre** (clôture produit / L9)
- **Décideurs** : Devin (connecteurs)
- **Portée** : `app/connectors/plugins.py`, `pyproject.toml`, `tests/unit/connectors/test_plugin_discovery.py`, `tests/integration/test_plugin_absent_degrades.py`

## Contexte et problématique

§9.2 exclut de la V1 l'OCR avancé, l'audio, la vidéo et le streaming temps réel,
mais exige qu'ils soient **prévus comme plugins**. Sans mécanisme d'enregistrement,
ajouter un connecteur obligerait à modifier le cœur (`app/connectors/`,
`pipeline_runner`) — précisément ce que la spec interdit pour ces capacités
« à venir ».

## Décision

1. Un connecteur externe s'enregistre via le groupe de points d'entrée
   **`inis.connectors`** (déclaré dans `pyproject.toml`), sans toucher le cœur.
2. Le contrat d'un point d'entrée est une **fabrique** — un appelable (généralement
   une classe) qui renvoie un objet satisfaisant `SourceConnector`
   (`app/connectors/base.py`, §9).
3. Le registre `app/connectors/plugins.py` découvre **paresseusement** la
   métadonnée installée (`importlib.metadata.entry_points`), instancie à la demande
   (`load_plugin`) et ne masque **jamais** un point d'entrée cassé : un plugin qui
   ne charge pas échoue bruyamment, il ne disparaît pas de la liste des capacités.
4. Un connecteur dont le moteur n'est pas installé **déclare** sa capacité
   (`metadata().supported_source_types == ["ocr"]`) mais **refuse** ses opérations
   (`NotImplementedError` nommé), jamais ne fabrique de contenu.

## Conséquences

- Ajouter un connecteur = publier un paquet avec un point d'entrée
  `inis.connectors` → aucune modification du dépôt INIS.
- Le cœur reste figé ; la démonstration `ocr` vit dans les tests (fixtures), pas
  dans le code de production, pour ne pas transformer le système en marketplace.
- `plugin_names()` offre une liste triée des connecteurs installés, exposable par
  une future route de capacité sans effort supplémentaire.
