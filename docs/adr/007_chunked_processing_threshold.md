# ADR 007 : Seuil de Découpage Chunking Obligatoire (§11, §21)

- **Statut** : accepté, **mis en œuvre** (lot L2.6, §41.6)
- **Décideurs** : Codex (ingestion), Devin (§41.6)
- **Portée** : `app/knowledge/normalization/limits.py`,
  `app/knowledge/ingestion/document_ingestor.py`, `configs/*.toml`

## Contexte et Problématique
Le traitement de documents volumineux ou de grands jeux de données dépasse les fenêtres de contexte des modèles et provoque une saturation mémoire.

## Décision
- Définir un seuil strict `max_information_units_per_request` (défaut : 50).
- Au-delà de ce seuil, le découpage en tronçons (**chunking**) devient obligatoire avant tout passage en analyse ou extraction.
- Chaque fragment conserve son lignage d'origine via les métadonnées de fragment (`document_fragment`).

## Mise en œuvre (L2.6)

Le seuil n'est plus une phrase : il est **lu** et **appliqué**.

1. **Où le seuil vit** — `app/knowledge/normalization/limits.py` :
   `DEFAULT_MAX_INFORMATION_UNITS_PER_REQUEST = 50`, surchargeable par
   `MAX_INFORMATION_UNITS_PER_REQUEST` (même convention que
   `MAX_PLAN_STEPS` dans `app/planning/limits.py`). Chaque `configs/*.toml`
   porte `[limits].max_information_units_per_request = 50` et
   `tests/unit/core/test_config.py` vérifie que le profil et le runtime ne
   divergent pas. Une valeur illisible (absente, non entière, `<= 0`) retombe
   sur le défaut : un seuil que personne ne peut énoncer n'est pas un seuil.
2. **Qui découpe** — `chunked_processing_config()` traduit le seuil en bloc
   `[CONFIG]` §41.6 : `max_in_memory_rows = chunk_size_rows = seuil`,
   `parallel_chunks = 4` (défaut §41.6). `DefaultChunkedDatasetProcessor`
   (déjà écrit, C18) est donc atteint par le **chemin réel** :
   `ingest_document()` construit les unités §11 tronçon par tronçon dès que le
   nombre de lignes/pages dépasse le seuil, puis fusionne les résultats dans
   l'ordre des tronçons.
3. **Ce que le découpage borne** — la **construction des unités** (un `ULID`,
   une validation d'entité §11 par ligne/page). Il ne borne pas le schéma du
   `Dataset` : §41.6 ne fournit pas de fusion incrémentale de schéma, le schéma
   reste inféré des lignes rendues par le lecteur. Cette limite est écrite dans
   le code (`_chunked_units`, `ingest_document`), pas sous-entendue.
4. **Le lignage** — chaque unité porte sa position (§11) : `row` +
   `sheet` (classeur), `page` (PDF), `paragraph`/`table` (DOCX), `section`
   (texte) et le décalage de caractères dans le texte extrait. Les unités de
   prose sont de type `document_fragment`, celles d'un tableau `record` : le
   récit (`document_fragment`) reste distinct du fait atomique.
5. **Transparence** — en deçà du seuil, aucun processeur n'est instancié ; au
   delà, le résultat est **identique** (mêmes unités, même ordre), ce qui est
   verrouillé par `tests/unit/knowledge/test_ingestion_chunking.py` et
   `tests/integration/test_chunked_ingestion.py`.

## Conséquences

- Un fichier de 5 000 lignes produit 5 000 unités construites par paquets de 50 :
  la mémoire de travail est bornée par le tronçon, pas par le fichier.
- Le seuil est visible par le déploiement (TOML + variable d'environnement),
  donc testable et ajustable sans toucher au code.
- Un enregistrement qui ne peut pas devenir une unité §11 est **nommé** dans
  `limitations` (§25.2) au lieu d'interrompre l'ingestion du reste du fichier.

## Limites assumées

- `max_in_memory_bytes` conserve son défaut §41.6 (512 Mio) : un document
  téléversé est déjà borné par `[limits].max_upload_bytes` (§36.6), le seuil de
  lignes est celui qui peut réellement être franchi.
- Le traitement des tronçons est exécuté séquentiellement (`run()` attend chaque
  tronçon) : `parallel_chunks` borne les tronçons en vol, il n'ordonnance pas de
  parallélisme réel aujourd'hui.

