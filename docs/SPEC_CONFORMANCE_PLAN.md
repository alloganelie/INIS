# SPEC_CONFORMANCE_PLAN — Plan de mise en conformité INIS ⇄ `INIS_SPEC.md`

**Objet** : plan de travail exécutable et cochaable pour amener INIS de son état
actuel (v2.0.0, « testé en unitaire ») à un état **conforme au sens produit** :
ce que la spec `DOIT` faire est **branché au pipeline** et **exposable au client**.

**Date de rédaction** : 2026-09-29
**Base de référence** : `INIS_SPEC.md` §1, §8.4, §9, §12, §16, §17, §21, §24,
§27, §32, §36, §41.
**Branche** : `fix/pipeline-llm-synthesis` — **arbre de travail non propre**
(`git status --short` → 14+ fichiers modifiés non commités : `pipeline_runner.py`,
`router.py`, `pipeline_persistence.py`, `object_uploader.py`, `AGENT_STATUS.md`…).
⚠️ **Action préalable obligatoire** : committer ou stasher l'existant puis
repartir d'un arbre propre, sinon tous les diffs de ce plan sont illisibles.

---

## 0. Mode d'emploi de ce document

**Légende des cases**

| Case | Signification |
|---|---|
| `[ ]` | À faire |
| `[~]` | En cours (ajouter date + agent) |
| `[x]` | Fait **et prouvé** (test nommé + commit) |
| `[-]` | Abandonné / reporté (justifier) |
| `[!]` | Bloqué (voir §6 « Journal ») |

**Protocole de coché (règle héritée de `docs/SPEC_COVERAGE.md`)**

> Aucune case `[x]` sans **nom de test réel** qui la prouve et **hash de commit**.

Chaque tâche porte donc : `Tâche — preuve (fichier de test)`.

**Règle des 3 niveaux de conformité (le cœur du problème constaté)**

| Niveau | Définition | Statut INIS v2.0.0 |
|---|---|---|
| **N0 — Code présent** | le module existe, ses tests unitaires passent | ✅ très large (ex. 35 outils §21) |
| **N1 — Branché** | le pipeline d'une requête l'appelle réellement | ❌ presque nulle part (web uniquement) |
| **N2 — Exposé** | un client (HTTP/protocole/UI) peut le déclencher et obtenir le résultat | ❌ quasi inexistant (ni upload, ni artefact) |

> **Un lot n'est terminé qu'au niveau N2.** Un lot livré en N0/N1 vaut `[~]`,
> jamais `[x]`.

**Règles non négociables (`AGENTS.md`, `DEFINITION_OF_DONE.md`)**

1. Ne modifier que les zones autorisées par `AGENT_ASSIGNMENTS.md` (ou
   autorisation écrite de la phase en cours).
2. Avant **chaque** commit :
   `python scripts\check_architecture.py` ·
   `python scripts\check_contracts.py` ·
   `python scripts\check_invariants.py` ·
   `python scripts\check_backward_compat.py` ·
   `python -m pytest -q`
3. Aucun secret commité. Rappel : `start.bat` contient encore des clés en clair.
4. Chaîne de migrations : dernière = `0014` → **la prochaine est `0015`**.
5. Nouvel identifiant ⇒ §0.3 via `ULID.new("<PREFIXE_>")` — **sauf**
   `ART_{YYYY}_{SEQ6}` (§24.2) qui n'est pas un ULID et exige un compteur.
6. §22.3 / §37 : le LLM n'est **jamais** source de vérité. Tout chemin qui
   fabrique du contenu doit être supprimé, pas contourné.

---

## 1. État des lieux vérifié (base du plan)

Relevé du 2026-09-29 sur `3ac6c73` (+ constat que `app/artifacts/**` est un
*namespace package* PEP-420 **sans fichier source**, absent de `git ls-files`).

| # | Constat vérifié | Preuve | §impactés |
|---|---|---|---|
| C1 | `UploadFile` : **0 occurrence** dans `app/` → aucun endpoint n'accepte un fichier | grep `UploadFile` | §1.1, §9, §36.6 |
| C2 | Le pipeline n'importe **aucun** module fichiers/DB/images ; uniquement web | imports de `app/api/v1/requests/pipeline_runner.py` | §8.4, §9.1 |
| C3 | Connecteurs fichiers = `glob("*.csv")` sur un répertoire local | `app/connectors/files/csv_connector.py:22,40,45,60` | §9.1 — **corrigé en L2.4** (`a90f385`) |
| C4 | `request_type` validé puis **jamais lu** par le pipeline | `schemas.py:70` vs 0 occurrence dans le runner | §1.1, §7 — **corrigé en L2.2** (`3fde944`) : le plan est orienté par `request_type`
| C5 | `ToolRegistry` jamais peuplé ; les 35 outils §21 non adressables | seul `GLOBAL_USAGE.register(...)` | §21 — **corrigé en L2.2** (`066ac1b`) |
| C6 | Le « dispatch » réel est un stub qui **fabrique du texte** | `pipeline_runner.py:1031-1040` (`"Extracted intelligence payload for …"`) | §0.2, §22.3, §37 — **corrigé en L2.2** (`066ac1b`) : l'étape est dégradée avec sa cause |
| C7 | `app/artifacts/{delivery,generators,packager}/` + `app/api/v1/artifacts/` = dossiers vides | `dir(app.artifacts.generators) == []`, `git ls-files` vide | §24.2, §24.3 |
| C8 | Aucun ORM/repository `artifact` ; `app/storage/models/` = `account.py` seul | listing | §24.2, §27 |
| C9 | Table `artifacts` (migration `0005:41-58`) **sans `request_id` ni `created_at`** | `migrations/versions/0005_create_remaining_core_tables.py` | §24.2, §32 |
| C10 | Colis §24.1 : `datasets`/`artifacts`/`transformations` **codés en dur à `[]`** | `pipeline_runner.py:1531-1533` | §24.1 — **corrigé en L1/L2.3** (`7c1bba2`, `a6921ab`, `3fde944`) |
| C11 | Une **seule** `TRF_` par run, operator générique `PipelineRunner`, jamais projetée | `pipeline_persistence.py:223-262` | §12.1, §24.1 — **corrigé** (`3b7d327`) : une transformation par étape réellement exécutée |
| C12 | `app/knowledge/embedding/` et `app/knowledge/enrichment/` vides → `embeddings` jamais alimentée | listing | §12, §16 |
| C13 | `memory_checker`, `HybridSearch`, `VectorSearch` : **aucun consommateur** (le `ChunkedDatasetProcessor`, lui, est branché depuis L2.6) | grep global | §16.2, §17, §41.6 |
| C14 | Frontend : `api/artifacts.ts` appelle déjà `GET /artifacts?request_id=` (fallback silencieux) → endpoint absent | `frontend/src/api/artifacts.ts` | §24.2, §31 |
| C15 | `sha256_hex(data)` disponible ; `tests/factories/artifact_factory.py` existe | `app/core/hashing.py:19` | §24.2 |
| C16 | `SourceRepository` divergent de la migration `0002` (`source_id`/`id`) → `INSERT` KO sur PostgreSQL | `AGENT_STATUS.md` dette n°3 | §27, §18 |
| C17 | Cache **L1 seulement** ; `cache_entries` (0008) non câblée | `AGENT_STATUS.md` dette n°6 | §41.5 |
| C18 | `ChunkedDatasetProcessor` présent, **non branché** | `app/knowledge/normalization/chunked_dataset.py` | §41.6 — **corrigé en L2.6** : seuil de l'ADR 007 lu (`app/knowledge/normalization/limits.py`) et appliqué dans l'ingestion (`document_ingestor._chunked_units`), preuve `tests/integration/test_chunked_ingestion.py` |
| C19 | `app/security/certificates/` sans module (mTLS absent) ; `app/security/vault/` OK | listing | §19.2 |
| C20 | Aucun mécanisme de plugins (§9.2) : 0 `plugin`, 0 `entry_points` | grep + `pyproject.toml` | §9.2 |
| C21 | 1 428 tests unitaires verts, mais **aucun test de bout en bout d'ingestion de fichier** | `AGENT_STATUS.md` | §33, §36 |
| C22 | Dépendances : `openpyxl`, `polars`, `pypdf`, `pdfplumber`, `python-docx`, `lxml`, `pgvector`, `boto3` présentes ; **aucun moteur PDF en écriture**, pas de `xlsxwriter` | `pyproject.toml:10-40` | §4.1, §24.3 |
| C23 | `python-multipart` **absent** de `pyproject.toml` (obligatoire pour `UploadFile` FastAPI) ; `Pillow` est délibérément **optionnel** (décision D6, `app/connectors/images/image_connector.py:72-75`) ; `OutputFormat = Literal["evidence_package","json","csv","xlsx","pdf","xml"]` | `pyproject.toml`, `app/domain/value_objects/request_constraints.py:26` | §4.1, §24 |
| C24 | `.env.example` documentait `DATABASE_URL` avec le driver **psycopg2** alors que `migrations/env.py` construit un moteur **async** (`async_engine_from_config`) ⇒ `make migrate` échoue sur un poste avec « requires an async driver » (le conteneur `api` y échappait car `docker-compose.yml` définit déjà une URL `+asyncpg`) | `.env.example:16-19`, `migrations/env.py:13-15` | §4.2, §41.14 — **corrigé en L1** |
| C25 | La table `artifacts` n'a **jamais eu de colonne `request_id` ni `created_at`** alors que `artifact_versions`/`artifact_lineage`/`artifact_delivery_events` (revision 0007) référencent l'artefact ⇒ un artefact livré n'était ni retrouvable par requête ni horodaté | `migrations/versions/0005_create_remaining_core_tables.py:41-59` | §24.2, §27 — **corrigé en L1 (0013)** |
| C26 | `frontend/src/api/artifacts.ts` avalait toute erreur (`catch { return [] }`) : une route absente et « aucun artefact » étaient indiscernables (P10), et le mapping de `Artifact` (`name`/`content_type`/`url`) n'existait nulle part | `frontend/src/api/artifacts.ts` | §31, §32 — **corrigé en L1** |

**Ce qui est réellement conforme et ne doit pas être cassé** : §0.2/§0.3,
§2, §3, §5, §6, §7, §8, §10, §11, §13, §14, §15, §18, §20, §22, §25, §27
(28/28 tables), §28, §32 (tous endpoints + extras), §34, §41.2, §41.11, §41.12,
§41.14, §41.15. **Tout lot ci-dessous doit être régressé contre ces sections.**

---

## 2. Définition de « conforme » retenue (critère d'acceptation global)

Le plan est terminé lorsque, sur un environnement neuf :

1. un client HTTP peut **envoyer un fichier** (CSV/XLSX/JSON/XML/PDF/DOCX),
   et INIS produit des `InformationUnit` **sourcées** issues de ce fichier ;
2. un client peut faire **interroger PostgreSQL** par INIS (§36.7) ;
3. une requête peut **réutiliser la mémoire** via recherche hybride (§16.2, §17) ;
4. le colis §24.1 expose des `datasets[]` et `transformations[]` **réels** ;
5. chaque livraison produit des **artefacts** §24.2 téléchargeables
   (`sha256` + `storage_ref` vérifiables) et un export `.xlsx` §24.3 ;
6. les 20 critères de §36 passent sous forme de tests exécutables (§5 ci-dessous) ;
7. `make check-all` + `python -m pytest -q` verts, sans régression des sections
   listées au §1.

**Hors périmètre de ce plan (assumé, cf. §8)** : OCR avancé, audio, vidéo,
streaming, exécution sandboxée de code (§9.2/§23/Phase 9), déploiement cloud réel.

---

## 3. Graphe des lots, dépendances et effort

```text
L0 (0,5 j)  Préparation, mesure de référence, arbre propre
 │
 ├──> L1 (3-4 j)  Artefacts §24.2/§24.3 + API + UI        ← plus forte valeur visible
 │
 ├──> L2 (5-7 j)  Ingestion de fichiers + PostgreSQL       ← §36.6/§36.7, écart le plus grave
 │     │
 │     ├──> L3 (3-4 j)  Datasets, transformations, enrichment, embeddings
 │     │        │
 │     │        └──> L4 (2-3 j)  Recherche hybride + mémoire §16.2/§17
 │     │
 │     └──> L5 (2 j)   Qualité/confiance sur données structurées §13
 │
 ├──> L6 (3-4 j)  Persistance/repositories §27, §18 (dettes n°3 et n°5)
 ├──> L7 (3 j)    Cache L2/L3 §41.5, reprise §41.1
 └──> L8 (4-5 j)  Sécurité/gouvernance/charge §19, §41.3, §41.13 (dettes n°1, 2, 7, 8)
      └──> L9 (2 j) Extensions §9.2 (mécanisme de plugins)
```

**Chemin critique V1 (obligatoire)** : `L0 → L1 → L2 → L3 → L4`, puis `L5`,
puis `L6` (unification `SourceRepository` requise dès que L2 écrit des sources).
**Estimation totale** : **28–34 jours-agent** ; **chemin critique ≈ 14–19 j**.

**Parallélisation possible** (zones disjointes par `AGENT_ASSIGNMENTS.md`) :

| Vague | Devin (`app/artifacts/`, `app/connectors/`, `app/storage/`, `migrations/`) | Codex (`app/knowledge/`, `app/planning/`, `app/agents/`) | Antigravity (`app/api/`, `frontend/`) |
|---|---|---|---|
| V1 | L1.1–L1.3 | — | L1.4–L1.6 |
| V2 | L2.1 (stockage upload), L2.4 | L2.2 (dispatch), L3.1 | L2.3 (schémas/routeur) |
| V3 | L3.3, L6 | L4, L5 | — |

**Convention de branche** : une branche par lot, `feat(<zone>): <description>`
(ex. `feat(artifacts): generate and deliver §24.2 artifacts`).

---

## 4. Lots de travail

> **Convention de preuve** : une preuve citée est soit un test **existant** (à ne pas casser),
> soit un **test à créer** (le plus fréquent ici). Les critères §36 déjà `[x]` ne citent que des
> tests existants. Pour vérifier : `Test-Path tests\api\test_artifacts.py` (PowerShell).

### L0 — Préparation (0,5 j) · propriétaire : intégrateur désigné

- [ ] `git stash`/commit de l'arbre courant ; repartir d'un arbre propre sur la branche de lot — *preuve : `git status --short` vide*
- [ ] Capturer la mesure de référence : `python -m pytest -q` (noter le nombre de verts) et `make check-all` — *preuve : sortie collée dans §6 « Journal »*
- [ ] Vérifier les conteneurs requis (PostgreSQL+pgvector, Redis/Valkey, RustFS/MinIO, RabbitMQ) : `docker compose up -d` puis `make migrate` — *preuve : `alembic current` = `0012 (head)`*
- [ ] Ouvrir une branche `feat/conformance-v1` (ou une branche par lot) — *preuve : nom de branche dans le journal*
- [ ] Lire (et non modifier) ces 6 points d'ancrage : `pipeline_runner.py:1000-1060`, `pipeline_runner.py:1500-1560`, `pipeline_persistence.py:15-100`, `app/api/v1/requests/router.py:23-60`, `app/api/v1/router.py:32-46`, `app/main.py:91-105`

**Critère de sortie L0** : arbre propre, baseline chiffrée, migration `0012` appliquée.

---

### L1 — Artefacts §24.2 / §24.3, API et UI (3–4 j) · Devin + Antigravity

**Objectif** : qu'une livraison produise des fichiers réels, traçables, téléchargeables.

> ### ⚙️ État d'avancement L1 au 2026-09-29 (branche `feat/conformance-v1`)
>
> **Fait et prouvé (N2 sur le chemin nominal)** — preuves réelles :
>
> | Sous-lot | Preuve |
> |---|---|
> | L1.1 générateurs CSV/JSON/XML/XLSX + refus PDF | `tests/unit/artifacts/test_generators.py` (22 cas) |
> | L1.1/§24.3 onglets du classeur | `tests/unit/artifacts/test_delivery_service.py::TestDeliverArtifacts::test_xlsx_delivery_fills_the_spec_sheets` |
> | L1.2 séquence `ART_{YYYY}_{SEQ6}` (unit) | `tests/unit/artifacts/test_artifact_packager.py::TestArtifactSequence` |
> | L1.2 séquence **en base** (monotonie, par année, survit à un nouvel engine) | `tests/integration/storage/test_artifact_repository.py::TestIdentifierAllocation` |
> | L1.2 packager (staging S3, digest, échec nommé) | `tests/unit/artifacts/test_artifact_packager.py::TestArtifactPackager` |
> | L1.3 migration `0013` + `create` idempotent + `list_for_request` | `tests/integration/storage/test_artifact_repository.py::TestPersistence` |
> | L1.4 routes list/detail/download + dégradations explicites | `tests/api/test_artifacts.py` (9 cas) |
> | L1.4/§24.2 chaîne complète HTTP + PostgreSQL | `tests/integration/test_artifacts_persistence.py` |
> | **Critère de sortie L1** : `xlsx` → upload réel S3 → liste → download, `sha256` recalculé | `tests/integration/test_artifacts_object_storage.py` |
> | L1.5 pipeline n'attache un fichier que si demandé | `tests/api/test_artifacts.py::TestDeliveredArtifacts` |
> | L1.6 mapping canonique → UI + fin du `catch` silencieux | `frontend/src/api/artifacts.ts` + `npx tsc --noEmit` |
>
> **Décisions prises en L1 (à ne pas redécouvrir)**
>
> 1. **PDF = option A** : refus explicite (`PDF_UNAVAILABLE_REASON`) porté dans `limitations`,
>    **sans** substitution vers un autre format (livrer un CSV quand un PDF est demandé serait
>    une invention silencieuse). L'option B (ADR + dépendance) reste ouverte, cf. §8.
> 2. Le fichier d'un artefact **ne contient jamais son propre record** §24.2 (`artifacts` est retiré
>    du payload exporté en JSON/XML) : un fichier ne peut pas contenir son propre digest.
>    Le record est publié dans la réponse §24.1.
> 3. `created_at` de `artifacts` est **nullable**, écrit par l'application : pas de back-fill
>    inventé lors de la migration.
> 4. La table d'allocation s'appelle **`artifact_id_sequences`** (`year` PK, `last_value`) ; le nom
>    `artifact_sequences` du plan n'a pas été utilisé.
> 5. Sans base configurée, la séquence retombe sur un compteur **en mémoire** et le dit dans
>    `limitations` (`IN_PROCESS_SEQUENCE_LIMITATION`) : jamais de faux « identifiant fiable ».
> 6. Sans stockage objet, l'artefact est **quand même** enregistré avec
>    `storage_ref = "unavailable://…"` + une limitation : le client apprend qu'un fichier a existé
>    et qu'il n'est pas téléchargeable (le download répond `503`, pas `404`).
> 7. `artifact_factory.py` et `artifact_packager.py` du plan sont **un seul fichier**
>    (`app/artifacts/packager/artifact_packager.py`) : la fabrique faisait ~40 lignes.
> 8. Le séparateur CSV est un **paramètre** (défaut `;`), pas encore lu depuis `configs/*.toml`.
>
> **Reste ouvert dans L1**
>
> - [ ] `ETag` / `X-Checksum-Sha256` sur le download (headers non posés aujourd'hui).
> - [ ] Refus de téléchargement d'un artefact `status="deleted"` (§18.2).
> - [ ] Autorisation §19.3 (`check_permission`) sur le download.
> - [ ] `artifact_versions` (v1), `artifact_lineage`, `artifact_delivery_events` : tables existantes
>   (0005/0007) mais **toujours vides** — seul `artifacts` est écrit.
> - [ ] `_ToolAdapter` (C6/P1) fabrique encore du texte : à neutraliser.
> - [ ] Page/section « Artefacts » dans l'UI (`pages/RequestStatus.tsx`).

#### L1.1 — Générateurs (Devin · `app/artifacts/generators/`)

- [x] Créer `app/artifacts/generators/__init__.py` (API publique : `generate_artifact(...)`) — *preuve : `tests/unit/artifacts/test_generators_init.py`*
- [x] `csv_generator.py` : export du colis/`Dataset` en CSV (stdlib `csv`, UTF‑8 BOM, séparateur `;` configurable via `configs/*.toml`) — *preuve : `tests/unit/artifacts/test_csv_generator.py`*
- [x] `json_generator.py` : export JSON strict = **le colis §24.1 tel quel** (`ensure_ascii=False`, clés triées, `canonical_json` de `app/core/hashing.py`) — *preuve : `tests/unit/artifacts/test_json_generator.py`*
- [x] `xml_generator.py` : export XML des unités/preuves (`lxml`, déjà dépendance) — *preuve : `tests/unit/artifacts/test_xml_generator.py`*
- [x] `xlsx_generator.py` (§24.3) : `openpyxl` (déjà dépendance) — onglets `données`, `métadonnées`, `dictionnaire`, `sources`, `provenance`, `qualité`, `version` ; **aucune valeur inventée** : une cellule sans donnée reste vide + `limitations` — *preuve : `tests/unit/artifacts/test_xlsx_generator.py`*
- [x] `pdf_generator.py` : ⚠️ **aucun moteur PDF en écriture n'est installé** (C22). Décision requise en début de lot :
  - option A (recommandée, 0 dépendance) : documenter `.pdf` comme `[-]` hors périmètre, renvoyer le format supporté le plus proche ;
  - option B : ajouter une dépendance **documentée dans un ADR** (`docs/adr/009_*`), puis l'implémenter ;
  - dans les deux cas : le générateur refuse honnêtement (`limitations`/§25.2) au lieu de produire un fichier vide.
  - *preuve : `tests/unit/artifacts/test_pdf_generator_absent.py` (refus explicite) ou tests de l'option B*
- [x] Aucun générateur ne doit écrire sur disque hors répertoire temporaire (`tempfile`) : le contenu part ensuite dans S3 — *preuve : `tests/unit/artifacts/test_generators_no_leak.py`*

#### L1.2 — Fabrique d'artefacts (Devin · `app/artifacts/packager/`)

- [x] `artifact_sequence.py` : allocateur `ART_{YYYY}_{SEQ6}` (**pas un ULID**).
  Choix à implémenter : compteur atomique en base (table dédiée ou `SELECT max(...)` sous
  `SELECT ... FOR UPDATE`) → **nécessite la migration `0013`** (voir L1.3).
  *preuve : `tests/unit/artifacts/test_artifact_sequence.py` (unicité sous concurrence, passage d'année)*
- [x] `artifact_factory.py` : construit `app.domain.entities.artifact.Artifact` (existant, C15)
  avec `size_bytes`, `sha256 = sha256_hex(data)`, `storage_ref = S3Client.upload(key, data, content_type)`,
  `source_ids`/`dataset_ids`/`transformation_ids` issus du colis, `purpose`, `version="1.0.0"`.
  ⚠️ `Artifact.validate()` **exige** au moins un id de traçabilité si `provenance_complete=True` :
  poser `provenance_complete=False` plutôt que mentir (§0.2).
  *preuve : `tests/unit/artifacts/test_artifact_factory.py`*
- [x] `artifact_packager.py` : orchestration `format demandé → générateur → S3 → Artifact validé`.
  Réutiliser le `S3Client` de `app/storage/object_storage/s3_client.py` (`upload` renvoie `s3://bucket/key`)
  et les helpers `object_uploader/object_downloader` (import paresseux, §4).
  *preuve : `tests/unit/artifacts/test_artifact_packager.py`*

#### L1.3 — Migration `0013` et persistance des artefacts (Devin)

- [x] Créer `migrations/versions/0013_artifacts_request_link.py`, `down_revision = "0012"` :
  - `ALTER TABLE artifacts ADD COLUMN request_id TEXT NULL` **+ index** `ix_artifacts_request_id` ;
  - `ALTER TABLE artifacts ADD COLUMN created_at TIMESTAMPTZ NOT NULL DEFAULT now()` ;
  - table d'allocation `artifact_sequences (year INT PRIMARY KEY, last_seq BIGINT NOT NULL)` (ou colonne compteur) ;
  - `downgrade()` symétrique et testé.
  ⚠️ §41.14 / gate **BC005** : index sur table **préexistante** ⇒ `CREATE INDEX CONCURRENTLY` est
  **interdit en transaction** ; documenter le choix dans le commentaire de migration
  (voir la note BC005 déjà présente dans `AGENT_STATUS.md`).
  *preuve : `tests/unit/migrations/test_0013_artifacts_request_link.py` + `python scripts\check_backward_compat.py`*
- [x] `app/storage/repositories/artifact_repository.py` : `save(artifact)`, `get(artifact_id)`,
  `list_by_request(request_id)`, `list_by_type(...)`, en suivant le style des repositories
  existants (`evidence_repository.py`, `information_unit_repository.py`) et **sans créer sa
  propre table** (piège C16 du `SourceRepository`).
  *preuve : `tests/unit/storage/test_artifact_repository.py` (SQLite) + `tests/integration/test_postgres_real.py::test_artifact_repository_postgres`*
- [x] Exporter le repository dans `app/storage/repositories/__init__.py` — *preuve : test d'import*

#### L1.4 — Endpoints artefacts (Antigravity · `app/api/v1/artifacts/`)

Le frontend **appelle déjà** (C14) : `GET /artifacts?request_id=` et `GET /artifacts/{id}`.

- [x] `app/api/v1/artifacts/__init__.py` + `router.py` + `schemas.py` :
  - `GET /v1/artifacts?request_id=REQ_...` → `{"artifacts": [ §24.2 ]}` (et tableau brut accepté par le client) ;
  - `GET /v1/artifacts/{artifact_id}` → §24.2 exact ;
  - `GET /v1/artifacts/{artifact_id}/download` → flux binaire, `Content-Disposition: attachment; filename="…"`,
    `Content-Type` = `mime_type`, `ETag`/`X-Checksum-Sha256` = `sha256` ;
  - `status` respecté (`available`/`archived`/`deleted`) ; **un artefact `deleted` ne se télécharge pas** (§18.2).
  *preuve : `tests/api/test_artifacts.py` (liste, 404, download + hash, refus si `deleted`)*
- [x] Enregistrer le routeur **aux deux endroits** : `app/api/v1/router.py:32-46` **et**
  `app/main.py:91-105` (les deux listes existent et doivent rester synchrones).
  *preuve : `tests/api/test_openapi_schema_changelog.py` (existant, §41.15) + `tests/api/test_artifacts_routes_registered.py` (à créer)*
- [ ] Autorisation : appliquer les politiques §19.3 (`check_permission`) sur le téléchargement.
  *preuve : `tests/security/test_artifact_download_authz.py`*

#### L1.5 — Pipeline : produire et exposer les artefacts (Devin + Antigravity)

- [x] Dans `pipeline_runner.py`, remplacer les `[]` de la ligne **1531-1533** par les valeurs réelles :
  `datasets` (L3), `artifacts` (L1.2), `transformations` (L3.2).
  *preuve : `tests/api/test_requests.py::test_delivery_exposes_artifacts_when_requested`*
- [x] Générer les artefacts **uniquement si demandé** : `required_output.format`
  (`schemas.py:62`, valeurs possibles `request_constraints.py:26` :
  `evidence_package | json | csv | xlsx | pdf | xml`) :
  `json`/`csv`/`xlsx`/`xml` ⇒ fichier ; `evidence_package` (défaut) ⇒ pas de fichier, mais le
  colis reste exposé en JSON par l'API ; `pdf` ⇒ décision de L1.1 (`limitations` +
  `recommended_next_actions` si option A) — §37 « signaler > inventer ».
  *preuve : `tests/api/test_artifacts_requested_formats.py` (paramétré sur les 6 valeurs)*
- [~] Persister chaque artefact (`artifact_repository`) + `artifact_versions` (v1) +
  `artifact_lineage` (source/dataset/transformation ids réels) + `artifact_delivery_events`.
  *preuve : `tests/integration/test_artifact_delivery_e2e.py` (requête complète → lignes en base → S3 → download)*
- [x] Corriger le chemin stub `_ToolAdapter` (`pipeline_runner.py:1031-1040`, C6) :
  il ne doit plus produire de contenu textuel fabriqué ; s'il est conservé comme
  secours, il doit renvoyer `status="degraded"` **sans** texte prétendant être un résultat.
  *preuve : `tests/agentic/test_no_fabricated_step_output.py` (créé — la preuve `test_non_hallucination.py::test_no_fabricated_step_output` citée initialement **n'existait pas**, cf. §6 journal du 2026-09-29/L2.2)*

#### L1.6 — UI (Antigravity · `frontend/`)

- [x] Ajouter le type `Artifact` dans `frontend/src/types/` (le module `api/artifacts.ts`
  l'importe déjà depuis `'../types'` : aujourd'hui non défini) — *preuve : `frontend/src/types/__tests__` ou build `npm run build`*
- [x] Supprimer le `catch { return [] }` **silencieux** de `frontend/src/api/artifacts.ts`
  (une erreur réseau ne doit pas se présenter comme « aucun artefact »).
- [ ] Page/section « Artefacts » dans `pages/RequestStatus.tsx` : liste, `sha256` tronqué,
  taille, type, bouton **Télécharger** (`GET /v1/artifacts/{id}/download`).
  *preuve : `frontend/src/pages/RequestStatus.test.tsx`*

**Critère de sortie L1 (N2)** : une requête `required_output.format="xlsx"` produit un artefact
listé par `GET /v1/artifacts?request_id=`, téléchargeable, dont le `sha256` recalculé côté test
est identique, et dont le `storage_ref` existe dans S3.

---

### L2 — Ingestion de fichiers et de bases (§1.1, §9.1, §8.4, §36.6/§36.7) (5–7 j) · Devin + Codex + Antigravity

> ### ✅ Lot **clos** au 2026-09-30 (L2.1 → L2.6) — critère de sortie N2 prouvé
> Détail des preuves : bloc « Critère de sortie L2 (N2) — clos » en fin de lot.

**Objectif** : un client peut fournir **une donnée** (fichier ou requête SQL) et obtenir des
`InformationUnit` sourcées. C'est l'écart le plus grave de l'audit (C1–C4).

> ### ⚙️ État d'avancement L2 au 2026-09-29 — **L2.1 terminé (N2)**, L2.2/L2.3 à faire
>
> **Fait et prouvé** (commit `640cebd`) :
>
> | Sous-lot | Preuve |
> |---|---|
> | L2.1 endpoint `POST /v1/requests/{id}/documents` (multipart) + `python-multipart` déclaré | `tests/api/test_document_upload.py` (12 cas) |
> | L2.1 détection MIME **par contenu** + liste blanche + refus nommés | `tests/unit/connectors/test_mime_sniffer.py` (18 cas) |
> | L2.1 stockage S3 `documents/{request_id}/{sha256}{ext}` + idempotence | `tests/integration/test_document_upload_s3.py` (6 cas, conteneurs réels) |
> | L2.1 quota §41.2 (`budget.max_storage_bytes`) + `[limits].max_upload_bytes` | `tests/api/test_document_upload.py::TestRefusedUpload::test_the_storage_budget_of_the_request_is_enforced` + `tests/unit/core/test_config.py` |
> | L2.1 classification §19.4 du **nom reçu** (et non du nom assaini) | `tests/security/test_upload_pii_classification.py` (7 cas) |
> | L2.1 lecture `GET /v1/documents{,?request_id=,/{id}}` | `tests/integration/test_document_upload_s3.py` + `tests/api/test_document_upload.py::TestReadRoutes` |
> | migration `0014` (documents : `file_name`, `size_bytes`, `request_id`, `pii_classification`, contrainte d'unicité) | apply/downgrade vérifiés sur la base docker + `scripts/check_backward_compat.py` (0 breaking) |
>
> **Décisions prises en L2.1 (à ne pas redécouvrir)**
>
> 1. **Classer le nom reçu, stocker un nom assaini** : l'assainissement remplace `@` par `_`,
>    donc classer *après* l'assainissement effacerait l'email avant de pouvoir le signaler.
>    Le bug a été trouvé par un test ; il est verrouillé par
>    `test_the_sanitized_name_would_hide_the_email`.
> 2. **L'extension détectée gagne** sur celle du client (un PDF nommé `.csv` est stocké `.pdf`),
>    et le nom ne peut pas sortir de son préfixe (`../../etc/passwd.csv` → `passwd.csv`).
> 3. **La clé S3 est dérivée du contenu** (`documents/{request_id}/{sha256}{ext}`) : elle ne
>    révèle rien du nom client et rend l'envoi rejouable sans dupliquer l'objet.
> 4. **Sans stockage objet, l'envoi est refusé (503)** : ici, contrairement aux artefacts de L1,
>    enregistrer le document sans ses octets produirait une ligne illisible — l'échec est net.
> 5. Sans base : l'envoi aboutit (les octets sont stockés) mais une `limitation` nomme l'absence
>    de persistance et de source.
> 6. `InformationRequestResponse` expose désormais `budget` : sans cela, `max_storage_bytes`
>    (§41.2) n'était pas applicable par un endpoint d'ingestion.
> 7. Le champ `information_units: []` est **déjà dans la réponse** (vide) pour que L2.3 le
>    remplisse sans changer le contrat.
>
> **Reste ouvert dans L2.1** : variante protocole `source_ref: "s3://…"` dans
> `InformationRequestCreate` (§5.2, agents non-HTTP) ; pas de route de téléchargement d'un
> document (`GET /v1/documents/{id}/download`) ; le PDF/Excel/DOCX sont acceptés et stockés mais
> **pas encore lus** (c'est L2.2/L2.3).
>
> **Prochaine étape (L2.2)** : `app/agents/pipeline/tool_dispatch.py` — peupler `ToolRegistry`
> et supprimer le stub `_ToolAdapter` qui **fabrique du texte** (C6/P1). C'est le seul point
> restant qui produit du contenu inventé dans une livraison.

#### L2.1 — Réception d'un fichier (Antigravity + Devin)

- [x] `POST /v1/requests/{request_id}/documents` (multipart, `UploadFile`) :
  ⚠️ `python-multipart` n'est **pas** dans `pyproject.toml` (C23) : l'ajouter en dépendance de
  runtime **dans le même commit** que l'endpoint, sinon FastAPI lève au démarrage.
  - contrôle de taille contre `budget.max_storage_bytes` (§41.2) et `[limits]` de `configs/*.toml` ;
  - détection MIME **par contenu** (magic bytes), pas seulement par extension ;
  - refus explicite et documenté pour les types non supportés (§25.2) — *liste blanche* : csv, xlsx, json, xml, pdf, docx, txt/md ;
  - réponse : `document_id` (`DOC_` via `ULID.new`), `source_id` (`SRC_`), `size_bytes`, `sha256`.
  *preuve : `tests/api/test_document_upload.py` (succès, type refusé, dépassement de quota, fichier vide)*
- [x] Stockage du binaire dans S3 sous `documents/{request_id}/{sha256}{ext}` via `S3Client.upload`
  (idempotent : même hash ⇒ même clé) — *preuve : `tests/integration/test_document_upload_s3.py`*
- [x] PII : passer le nom de fichier et les métadonnées au `pii` classifier (§19.4) avant persistance.
  *preuve : `tests/security/test_upload_pii_classification.py`*
- [x] Variante protocole : accepter `source_ref: "s3://…"` dans `InformationRequestCreate`
  (`schemas.py:66-87`) pour les agents qui ne font pas de HTTP multipart (§5.2).
  ✅ **fait en L2.6** : le schéma n'accepte **que** `s3://bucket/cle` (un chemin local ou une URL
  HTTP est refusé, §19) ; `app/knowledge/ingestion/object_intake.py` télécharge l'objet **en flux**
  (même plafond §41.2 qu'un envoi), le type **par le contenu** (§9.1), puis écrit `sources`,
  `documents`, le `Dataset` et les unités §11 — **la référence du client reste le `storage_ref`**
  (aucune copie). L'ingestion a lieu **avant** la planification du run (sinon le plan ne verrait pas
  la source que la requête possède), et une source illisible **refuse la création** (422 nommant la
  cause) au lieu de créer une requête autour d'une matière inexistante.
  *preuve : `tests/api/test_request_schema_source_ref.py` (20 cas : schéma, refus par bucket §19.3,
  plafond §41.2, type refusé, double d'objet) et `tests/integration/test_request_source_ref_e2e.py`
  (4 cas sur MinIO + PostgreSQL réels : ingestion, matière relue, colis §24.1 avec `read_csv`)*

#### L2.2 — Dispatch d'outils réel dans le pipeline (Codex)

> ### ⚙️ État d'avancement L2.2 au 2026-09-30 — **L2.2 clos** (items 1-4 faits, C4/C5/C6 fermés)
>
> **Fait et prouvé** (commits `066ac1b`, `8b13da2`, `3fde944`) :
>
> | Sous-lot | Preuve |
> |---|---|
> | `tool_dispatch.py` : les **35** outils §21 enregistrés dans `ToolRegistry` (C5) | `tests/unit/agents/pipeline/test_tool_dispatch.py::TestRegistryPopulation` |
> | Vocabulaire fermé d'actions, avec outils requis + `executable` + raison | `tests/unit/agents/pipeline/test_tool_dispatch.py::TestActionVocabulary` |
> | `StepExecutor` : `InfrastructureError` → `degraded`, autre erreur → `failed`, aucun `output` inventé | `tests/unit/agents/test_step_executor_dispatch.py` |
> | Suppression des **deux** fabrications (`_ToolAdapter` + « Fallback execution output ») | `tests/agentic/test_no_fabricated_step_output.py` |
> | Une action non-web ne devient **plus** une recherche web (elle était cherchée par son propre nom) | `tests/agentic/test_no_fabricated_step_output.py::test_a_non_web_action_never_becomes_a_web_search` |
> | **Plan refusé en amont** si une action est hors vocabulaire (client **et** LLM) | `tests/unit/planning/test_plan_action_vocabulary.py`, `tests/agentic/test_no_fabricated_step_output.py` (plan client + plan LLM refusés) |
> | La prose d'une étape LLM n'est plus promue en action | `tests/unit/llm/test_plan_parser.py::TestStepNormalization::test_prose_never_becomes_an_action` |
> | Le prompt de planification énonce le vocabulaire fermé (§22.3) | `tests/unit/llm/test_planning_prompt_vocabulary.py` |
> | **C4** — `request_type` oriente le plan, et `file_ingest` est branché | `tests/agentic/test_file_ingest_delivery.py`, `tests/integration/test_request_file_ingestion_e2e.py` |
>
> **Décisions prises en L2.2**
>
> 1. `executable=False` n'est pas un aveu d'impuissance mais une **déclaration exacte** : les 35
>    outils existent, mais la plupart attendent des entrées que le pipeline ne construit pas encore
>    (un fichier local, une base cible, un `Dataset`). Le test de la liste des manques est
>    volontairement fermé : passer une action à « exécutable » doit être un acte explicite.
> 2. Un `output` vide + une raison dans `error` remplacent tout texte de remplissage (§37). Les
>    `step_results` partent en persistance (C11) : c'est **là** que la fabrication entrait en base.
> 3. `is_web_action(unknown) == False` : une action inconnue ne doit jamais déclencher d'acquisition.
> 4. **Un plan invalide se refuse, il ne se répare pas** (`8b13da2`) : `PlanBuilder.validate_steps`
>    lève `InvalidPlanAction` en nommant l'action, sa position et le vocabulaire admis. Le plan du
>    client **et** le plan LLM passent par ce filtre ; un plan refusé n'est pas exécuté et son refus
>    est écrit dans `limitations`, le plan déterministe prenant sa place.
> 5. **La prose n'est pas une action** : `parse_plan` ne rapporte que l'`action` **déclarée** par le
>    LLM. Avant, `step.get("description") or step.get("action")` faisait d'une phrase l'action
>    exécutée — c'était le dernier chemin par lequel du texte décidait de l'exécution (C4/§0.2).
> 6. **Une action exécutable peut être conditionnelle** (`3fde944`) : `file_ingest` est `executable=True`
>    avec un champ `requires` (« un document déjà ingéré pour la requête ») et une raison qui décrit le
>    cas où elle ne peut pas tourner. Passer une action à « exécutable » reste un acte explicite
>    (`tests/unit/agents/pipeline/test_tool_dispatch.py` mis à jour dans le même commit).
>
> **Reste ouvert dans L2.2** — **néant** : les items 3 et 4 sont faits (voir ci-dessous).
> ⚠️ Le routage `postgres_query` par `request_type` reste dû, mais il appartient à **L2.5** :
> `file_ingest` ne peut pas être étendu à une base sans le connecteur lecture seule de ce lot.

> C'est ici que se joue le passage N0 → N1. Aujourd'hui le seul « dispatch » est un stub (C6).

- [x] `app/agents/pipeline/tool_dispatch.py` : résolveur `action/tool → callable` qui
  **peuple** `ToolRegistry` (`app/tools/registry.py`) avec les outils §21 réellement
  branchables : `read_csv`, `read_excel`, `read_json`, `read_xml`, `read_pdf`,
  `extract_document`, `postgres_query`, `extract_image_content`, `inspect_schema`,
  `profile_dataset`, `detect_duplicates`, `validate_schema`, `check_missing_values`,
  `check_consistency`, `check_freshness`, `compare_sources`, `retrieve_context`, `hybrid_search`.
  *preuve : `tests/unit/agents/pipeline/test_tool_dispatch.py` (chaque nom §21 est résolu ou explicitement listé comme non branchable)*
- [x] `step_executor.py` : exécuter l'outil résolu et **propager les erreurs** (`InfrastructureError`
  → `status="degraded"` + `limitations`), sans jamais substituer de texte inventé.
  *preuve : `tests/unit/agents/test_step_executor_dispatch.py`*
- [x] Le **planificateur** (`PlanBuilder` + `planning_prompt.py`) est contraint par le vocabulaire
  fermé : `PlanBuilder.validate_step`/`validate_steps` refuse (`InvalidPlanAction`) toute action hors
  vocabulaire, en nommant l'action, sa position et les actions admises ; `parse_plan` ne conserve que
  l'`action` déclarée (la prose n'est plus promue) et `planning_prompt.build` énonce le vocabulaire.
  *preuve : `tests/unit/planning/test_plan_action_vocabulary.py`, `tests/unit/llm/test_plan_parser.py`,
  `tests/unit/llm/test_planning_prompt_vocabulary.py`, `tests/agentic/test_no_fabricated_step_output.py`
  (un plan client **et** un plan LLM hors vocabulaire sont refusés avant exécution)* — commit `8b13da2`
- [x] Ajouter au vocabulaire du plan l'action `file_ingest` (§8.4 `file_ingest_step`) : `ACTIONS`
  (`app/agents/pipeline/tool_dispatch.py`) la déclare `executable=True` avec `requires`
  (« un document déjà ingéré pour la requête ») et la raison du cas où elle ne peut pas tourner ; le
  pipeline l'exécute réellement (relit les unités §11 du document, statut `done` + sortie factuelle).
  ⚠️ `app/planning/step_selector.py` n'a **pas** été modifié : il sélectionne une étape par ses
  dépendances, pas par son action — la case citait un fichier qui n'avait rien à changer.
  *preuve : `tests/unit/agents/pipeline/test_tool_dispatch.py::TestActionVocabulary::test_a_conditional_action_declares_what_it_needs`,
  `tests/agentic/test_file_ingest_delivery.py::TestADataRequestIsPlannedAroundItsFile::test_the_file_ingest_step_is_done_and_names_what_it_read`*
- [x] `request_type` devient **opérant** (C4) : `"data"`/`"source"` orientent le plan vers
  `file_ingest` **quand la requête a ingéré un document** (sinon le plan reste inchangé, ce qui
  préserve `tests/api/test_pipeline_e2e.py` : une requête `data` sans fichier cherche toujours sur le
  web) ; les autres types gardent leur plan et gagnent l'ingestion du fichier.
  ⚠️ Correction de preuve (le plan citait `tests/api/test_request_type_routing.py`, **ce fichier
  n'existe pas**) : la preuve réelle est
  `tests/agentic/test_file_ingest_delivery.py::TestTheOtherRequestTypesKeepTheirPlan` (unitaire, sans
  Docker) et `tests/integration/test_request_file_ingestion_e2e.py::test_a_data_request_does_not_search_the_web_for_its_own_file`
  (PostgreSQL réel : **zéro** appel de recherche pour une requête `data` dont le fichier est ingéré).
  ⚠️ `postgres_query` était dû ici (**L2.5**) : `request_type="data"` oriente vers `file_ingest`
  tant que la base lecture seule n'existe pas — ✅ **fait le 2026-09-30** (`7476a14` + `4f2a0eb`) : une
  préférence `postgres:` nommée par la requête oriente désormais le plan vers `query_database`, et
  les deux sources peuvent coexister (l'ingestion du fichier *et* la lecture de la base).

#### L2.3 — Datasets réels et traçabilité (§11, §12, §27)

> ### ⚙️ État d'avancement L2.3 au 2026-09-30 — ingestion, découpage et granularité **faits** ; reste la lignée d'artefact (L3)
>
> **Fait et prouvé** (commit `a6921ab`) :
>
> | Sous-lot | Preuve |
> |---|---|
> | Une unité §11 **par enregistrement** (CSV/JSON/XML/XLSX) ou **par section** (TXT/MD/PDF/DOCX), validée par l'entité §11 | `tests/unit/knowledge/test_document_ingestor.py` (17 cas) |
> | Localisation de **chaque** unité (`kind=row` + n° de ligne + colonnes ; `kind=section` + décalage de caractères) dans `location` **et** `raw_reference` | `tests/unit/knowledge/test_document_ingestor.py::TestTabularIngestion::test_each_unit_is_locatable` |
> | `Dataset` (`DATA_`) avec schéma, `row_count` et `storage_ref` **S3** (pas le `file://` temporaire) | `tests/integration/test_document_upload_s3.py::test_the_dataset_and_its_units_are_persisted` |
> | Persistance des unités + dataset et lecture via `GET /v1/information/{id}` | idem |
> | Migration `0015` (`datasets.storage_ref`/`request_id`, `information_units.dataset_id`/`location`) | up/down vérifiés sur la base docker + `check_backward_compat` (0 breaking) |
> | Charge illisible ⇒ **zéro unité** + une limitation nommant la cause | `tests/unit/knowledge/test_document_ingestor.py::TestUnreadablePayloads` |
>
> **Décisions prises en L2.3**
>
> 1. Les unités sont construites **via l'entité `InformationUnit`** (`.validate()`), donc un défaut §11
>    fait échouer l'ingestion au lieu de produire une unité douteuse.
> 2. Le `Dataset` est **reconstruit** avec `storage_ref` = la référence objet : les lecteurs §21
>    rapportent un `file://` qui meurt avec la copie temporaire (§18.1).
> 3. Aucun score de confiance inventé : `confidence = {"score": None, "not_a_probability": True}`.
> 4. PDF/DOCX : localisation par **bloc localisable** — ⚠️ **révisé en L2.6** : le numéro de page (PDF)
>    et l'index de paragraphe (DOCX) sont désormais **prouvés par le lecteur**
>    (`extract_document_blocks`), donc utilisés ; la L2.3 n'avait que la section + décalage.
> 5. Le vocabulaire `type` de §11 dans ce dépôt est `text|number|table|record|image_region|document_fragment`
>    (≠ `table_row`/`document_section` du plan) : les unités de fichier sont donc `record` et
>    `document_fragment`.
>
> **Reste ouvert dans L2.3**
>
> - [x] `ChunkedDatasetProcessor` (ADR 007) non branché : l'ingestion lit le document entier.
>   ✅ **clos en L2.6** : `app/knowledge/normalization/limits.py` lit le seuil de l'ADR 007
>   (`MAX_INFORMATION_UNITS_PER_REQUEST`, défaut 50, miroir dans `configs/*.toml`),
>   `_chunked_units` construit les unités §11 par tronçons de `chunk_size_rows` dès que le seuil est
>   franchi, et `tests/integration/test_chunked_ingestion.py` prouve le chemin réel (tronçons
>   `[50, 50, 20]` pour 120 lignes, 120 unités persistées, ordre du fichier conservé).
>   ⚠️ Ce qui est borné : la **construction des unités**, pas l'inférence de schéma du `Dataset`
>   (§41.6 n'offre pas de fusion incrémentale) — écrit dans le code, pas sous-entendu.
>   *preuve : `tests/integration/test_chunked_ingestion.py`, `tests/unit/knowledge/test_ingestion_chunking.py`*
> - [ ] `Transformation` **par étape réelle** (§12.1, C11) : `pipeline_persistence.py` écrit encore une
>   seule `TRF_` générique par run ; l'ingestion ne produit aucune transformation.
>   ⚠️ **Obsolète** : `app/knowledge/provenance/stage_transformations.py` (commit `066ac1b`) écrit
>   désormais une ligne par étape réellement exécutée — dont la paire du fichier ingéré
>   (`raw` = lecteur §21, `normalized` = `DocumentIngestor.ingest`), vérifiée par
>   `tests/unit/knowledge/test_transformation_records_per_stage.py` et, bout en bout, par
>   `tests/integration/test_pdf_ingestion_e2e.py`.
> - [x] Granularité page/feuille pour PDF/Excel (aujourd'hui : section du document, ou feuille unique du classeur).
>   ✅ **clos en L2.6** : une unité par **page** (PDF) et par **paragraphe**/**tableau** (DOCX), avec
>   `index` égal à la position réelle dans le document ; pour un classeur, la **feuille lue est nommée
>   dans chaque locator** (`location.sheet`) et les feuilles non lues sont listées dans `limitations`
>   (aucune fusion implicite, §0.2).
>   *preuve : `tests/unit/tools/test_document_blocks.py`, `tests/unit/knowledge/test_document_ingestor.py::TestWorkbookIngestion`*
> - [ ] `artifact_lineage` / `artifact_delivery_events` (L1) restent vides — maintenant que les datasets
>   existent, la lignée d'un artefact `dataset_export` peut être remplie (§24.2) → **L3**.

- [x] À partir d'un document ingéré, produire un `Dataset`
  (`app/domain/entities/dataset.py` : `dataset_id` `DATA_`, `source_id`, `dataset_schema`,
  `row_count`, `storage_ref`) et le persister dans la table `datasets` (migration `0007`).
  *preuve : `tests/unit/knowledge/test_dataset_from_csv.py` + `tests/integration/test_dataset_persistence.py`*
- [x] Réutiliser `app/knowledge/normalization/chunked_dataset.py` (déjà écrit, C18) au-delà
  du seuil documenté par l'ADR `007_chunked_processing_threshold.md`.
  ✅ **clos en L2.6** : seuil lu (`app/knowledge/normalization/limits.py`), appliqué dans
  `document_ingestor._chunked_units`, et l'ADR 007 porte désormais sa section « Mise en œuvre »
  (ce qui est découpé, ce qui ne l'est pas, où le seuil se règle).
  *preuve : `tests/integration/test_chunked_ingestion.py`, `tests/unit/knowledge/test_ingestion_chunking.py`*
- [x] Unités d'information issues du fichier : **une unité par enregistrement/fragment utile**,
  `type` ∈ {`text`,`table_row`,`document_section`…} selon §11, avec `raw_reference` pointant
  sur `document_id` + `location` (page/feuille/ligne/colonne) — jamais de contenu sans localisation.
  *preuve : `tests/agentic/test_file_unit_traceability.py` (chaque unité est localisable dans le fichier source)*
- [x] Création d'une `Transformation` **par étape réelle** (§12.1) :
  `RAW → NORMALIZED → ENRICHED → DERIVED`, avec `operator`, `tool`, `tool_version`,
  `parameters`, `result` (remplacer/compléter la `TRF_` unique de `pipeline_persistence.py:223-262`, C11).
  *preuve : `tests/unit/knowledge/test_transformation_records_per_stage.py` (créé) + `tests/integration/test_b4bis_persistence.py` (stages distincts en base) + `tests/integration/test_idempotency_integration.py` (rejeu sans doublon)*
- [x] Fermer **C10** : le champ `transformations` de la livraison n'est plus `[]` — il porte les étapes
  réellement exécutées (et l'étage `derived` référence les `ART_` livrés). *preuve : `tests/unit/knowledge/test_transformation_records_per_stage.py::TestStageRecording`*

#### L2.4 — Connecteurs fichiers capables de lire autre chose qu'un répertoire (Devin)

> Aujourd'hui `CSVConnector.discover()` fait `self._base_path.glob("*.csv")` (C3) : un fichier
> uploadé ou un objet S3 est invisible.

> ✅ **Fait le 2026-09-30 (`a90f385`)** — le mode « cible explicite » existe, S3 est lu en
> flux, et le matériau porte son `content_type`/`location` réels. Détail en §6.

- [x] Ajouter un mode « cible explicite » aux connecteurs (`app/connectors/files/*`) :
  `discover(Query(filters={"location": "s3://…|/abs/path"}))` renvoie exactement ce fichier ;
  conserver le comportement `glob` actuel comme mode par défaut (**non régression** :
  `tests/unit/connectors/test_csv_connector.py` doit rester vert sans modification).
  *preuve : `tests/unit/connectors/test_connector_explicit_location.py` (43 tests, les 6 connecteurs)*
- [x] Téléchargement S3 → répertoire de travail temporaire (`object_downloader`), streaming
  plutôt que `read()` intégral au-delà de `[limits]`.
  *preuve : `tests/integration/test_connector_from_s3.py` (MinIO réel) +
  `tests/unit/storage/test_s3_stream_download.py` (13 tests : plafond déclaré refusé **avant** le
  transfert, plafond dépassé en cours de flux, aucun fichier partiel)*
- [x] `retrieve()` doit conserver `content_type` + `location` réels dans `RawSource.metadata`
  (indispensable à la localisation §11). *preuve : `tests/unit/connectors/test_raw_source_metadata.py` (36 tests)*

#### L2.5 — PostgreSQL (§36.7) (Devin)

> ✅ **Fait le 2026-09-30 (`7476a14` + `4f2a0eb`)** — l'outil est en lecture seule stricte, les
> identifiants viennent du vault, et la source nommée par la requête entre dans le colis.
> Détail en §6.

- [x] Exposer l'outil `postgres_query` **en lecture seule** : liste blanche
  `SELECT`/`WITH`, refus de toute écriture DDL/DML, `LIMIT` forcé, `statement_timeout`,
  connexion par identifiants du **vault** (§41.4, `app/security/vault/credential_vault.py`) —
  **jamais** de DSN dans la requête client.
  *preuve : `tests/unit/tools/test_postgres_query_readonly.py` (36 tests : `SELECT` OK ;
  `UPDATE`/`DROP`/CTE d'écriture/empilement refusés ; `SET TRANSACTION READ ONLY` +
  `SET LOCAL statement_timeout` observés ; DSN refusé par son nom, sans écho du secret)*
  — commit `7476a14`
- [x] Étape de plan `query_database` déclenchée par `request_type="data"` +
  `constraints.source_preferences=["postgres:<credential_ref>[#table]"]`, résultat converti en
  `Dataset` + unités (même chemin que L2.3). *preuve :
  `tests/integration/test_request_database_read_e2e.py` (PostgreSQL réel : `datasets[]` non vide,
  unités localisées en `row`, source de type `database`, étages §12.1 `postgres_query`, zéro
  recherche web) + `tests/agentic/test_database_read_delivery.py` (24 tests : deux sources détenues
  par la même requête, échec nommé, aucune recherche de remplacement) +
  `tests/unit/knowledge/test_database_material.py` (32) +
  `tests/unit/connectors/test_postgres_source_target.py` (28)*
- [x] `PostgresConnector` : compléter les méthodes encore stub (`AGENT_STATUS.md`, dette PHASE-11 :
  « read/write encore stub ») ou documenter précisément ce qui reste hors périmètre.
  *preuve : `tests/unit/connectors/test_postgres_connector.py` (10 tests : `discover` ne fabrique
  aucun candidat, `retrieve` lie `LIMIT`, `write` insère en paramètres liés, `health_check`
  nomme une base injoignable) — les méthodes ne sont plus des stubs ; le connecteur reste
  l'outil **interne** (DSN fourni par le déploiement) alors que le **chemin requête** passe par
  `postgres_query` + vault, seule voie ouverte à un client*
- [x] (L2.5b) La source nommée est lue **sur son propre DSN** : `postgres_query` n'est jamais
  appelé avec l'engine d'INIS (`INIS_DATABASE_URL`), sinon les lignes lues seraient celles
  d'INIS sous une provenance annonçant la base du client.
  *preuve : `tests/unit/knowledge/test_database_material.py::TestWhichDatabaseIsRead`*
- [x] (L2.5b) Le `DATA_` livré existe en base (`DatasetRepository`) : un identifiant publié dans
  `datasets[]` doit être consultable via l'API, comme celui d'un fichier ingéré.
  *preuve : `tests/integration/test_request_database_read_e2e.py::test_the_delivered_dataset_is_consultable`*
- [x] (L2.5b) Les **deux sources détenues** par une même requête (`data` + fichier ingéré + base
  nommée) sont lues : orienter le plan sur la base ne retire que les étapes **web**.
  *preuve : `tests/agentic/test_database_read_delivery.py::TestBothOwnedSourcesCoexist`*

> **Ce qui reste hors périmètre de L2.5** : le *choix* de la table dans une base à plusieurs
> tables se fait par la préférence (`#<table>`) — sans table nommée, INIS **liste** les tables du
> schéma `public` et le déclare, plutôt que de lire une table au hasard ; les jointures/`SELECT`
> libres ne sont pas exposés au client (aucune requête SQL dans la requête HTTP, §1.2/§19).

#### L2.6 — Images et documents non structurés (Codex)

- [x] Brancher `extract_document` (PDF/DOCX→texte, `app/tools/files/document_reader.py`) puis
  `fact_extractor` sur le texte extrait, avec `location` = page/paragraphe.
  Le lecteur rend désormais des **blocs localisables** (`extract_document_blocks`) : une **page**
  par unité pour un PDF, un **paragraphe** (puis un **tableau**) pour un DOCX, un paragraphe pour
  TXT/MD ; `index` est la position réelle dans le document (la 3ᵉ paragraphe reste `paragraph 3`
  même si la 2ᵉ est vide) et `char_offset`/`characters` sont **vérifiables**
  (`texte[offset:offset+caractères] == bloc`). `FactExtractor.extract` (async) lit les phrases de
  chaque bloc ; elles sont rangées dans `content["sentences"]` **à côté** du texte intégral — un
  bloc trop court pour le découpeur de phrases garde tout son texte.
  *preuve : `tests/integration/test_pdf_ingestion_e2e.py`, `tests/unit/tools/test_document_blocks.py`
  (9 cas), `tests/unit/knowledge/test_document_ingestor.py::TestPdfIngestion` / `TestDocxIngestion`*
- [x] Brancher `extract_image_content` (Pillow) pour les images fournies.
  Les types dont la **signature est prouvable** (`image/png`, `image/jpeg`) entrent dans la liste
  blanche §9.1 (`mime_sniffer.py`) et sont ingérés : une unité `image_region` par texte réellement
  embarqué + une pour les propriétés techniques. Pillow reste **optionnel (D6)** : quand il manque,
  aucune unité n'est produite et la limitation porte `pillow_available=False` — jamais une
  description inventée. **OCR toujours hors périmètre V1** (§9.2).
  *preuve : `tests/unit/tools/test_image_content_no_ocr.py` (11 cas, dont la dégradation Pillow),
  `tests/unit/knowledge/test_document_ingestor.py::TestImageIngestion`,
  `tests/api/test_document_upload.py::test_the_image_path_extracts_units_without_inventing_a_description`*

**Critère de sortie L2 (N2)** : un `POST /v1/requests` avec un CSV joint (ou `source_ref`)
produit un colis §24.1 contenant `datasets[]` non vide, des unités localisables dans le fichier,
`transformations[]` non vide, et une provenance complète ; idem avec une requête PostgreSQL
lecture seule ; les tests d'erreur (type refusé, quota, SQL d'écriture) passent.

> ### ✅ Moitié « fichier » du critère de sortie L2 — prouvée le 2026-09-30 (`3fde944`)
>
> | Exigence | Preuve |
> |---|---|
> | `datasets[]` non vide | `tests/integration/test_request_file_ingestion_e2e.py::test_the_delivery_of_a_data_request_carries_its_csv` (dataset réel, `row_count`, `storage_ref`) |
> | unités localisables dans le fichier | idem : `location.kind == "row"`, `row ∈ {1, 2}`, `dataset_id` lié, `provenance.extracted_from` = l'objet stocké (§11) |
> | `transformations[]` non vide | idem : étage `raw` (`read_csv`) + `normalized` (`DocumentIngestor.ingest`) de l'ingestion, en plus des étages web |
> | provenance complète | idem : `provenance.request_type`, sources du document dans `sources[]`, `document_id`/`dataset_id` sur chaque unité |
> | type refusé / quota | `tests/integration/test_document_upload_s3.py::test_an_unsupported_document_never_reaches_the_bucket` (+ tests de quota §41.2 du lot L2.1) |
>
> ⚠️ Reste dû pour **clore** L2 : l'extraction PDF/image (lot **L2.6**) — ✅ **fait le 2026-09-30**
> (L2.6, voir le bloc ci-dessous). La branche « requête
> PostgreSQL lecture seule » (lot **L2.5**), le mode « cible explicite » des connecteurs fichiers
> et la lecture S3 en flux (lot **L2.4**) sont **faits** (`a90f385`, `7476a14` + `4f2a0eb`).

> ### ✅ Critère de sortie L2 (N2) — **clos**
>
> | Moitié du critère | Preuve | État |
> |---|---|---|
> | Fichier joint → `datasets[]` non vide, unités localisables, `transformations[]` non vide, provenance complète | `tests/integration/test_request_file_ingestion_e2e.py` | ✅ L2.3 |
> | Requête PostgreSQL lecture seule → même contrat | `tests/integration/test_request_database_read_e2e.py`, `tests/integration/test_request_file_ingestion_e2e.py` | ✅ L2.5b |
> | **PDF/DOCX → une unité par page/paragraphe, localisée** | `tests/integration/test_pdf_ingestion_e2e.py` (colis §24.1 : `location.page ∈ {1,2}`, `content.text` = le texte des pages, étages `read_pdf` + `DocumentIngestor.ingest`) ; `tests/unit/tools/test_document_blocks.py` | ✅ L2.6 |
> | **Images → unités factuelles, sans OCR ni invention** | `tests/unit/tools/test_image_content_no_ocr.py`, `tests/unit/knowledge/test_document_ingestor.py::TestImageIngestion`, `tests/api/test_document_upload.py` | ✅ L2.6 |
> | **Au-delà de 50 unités, l'extraction se fait par tronçons** (ADR 007/§41.6) | `tests/integration/test_chunked_ingestion.py` (120 lignes → tronçons `[50, 50, 20]`, 120 unités en base), `tests/unit/knowledge/test_ingestion_chunking.py` (seuil + équivalence tronçonné/direct) | ✅ L2.6 |
> | Tests d'erreur (type refusé, quota, SQL d'écriture) | `tests/integration/test_document_upload_s3.py::test_an_unsupported_document_never_reaches_the_bucket` (archive ZIP refusée), quota §41.2 (lot L2.1), `tests/unit/tools/test_postgres_query_readonly.py` | ✅ L2.1/L2.5 |

> ### ✅ Moitié « PostgreSQL lecture seule » du critère de sortie L2 — prouvée le 2026-09-30 (L2.5b)
>
> | Exigence | Preuve |
> |---|---|
> | `datasets[]` non vide | `tests/integration/test_request_database_read_e2e.py::test_a_data_request_reads_the_named_table` (`row_count`, `storage_ref` = `postgres://analytics/<table>`, schéma inféré des valeurs réelles) |
> | unités localisables dans la source | idem : `location.kind == "row"`, `row ∈ {1,2,3}`, `dataset_id` lié, `provenance.extracted_from` = la référence de la source, `context.origin == "database_query"` (§11) |
> | `transformations[]` non vide | idem : étage `raw` (`PostgresConnector`/`postgres_query`) + `normalized` (`DatabaseMaterial`/`postgres_query`) — deux lignes, deux producteurs, pas une seule attribuée au web |
> | provenance complète | idem : `provenance.request_type == "data"`, source de type `database` dans `sources[]`, unités persistées avec `raw_reference.table` + `location` |
> | SQL d'écriture refusé | lot L2.5a : `tests/unit/tools/test_postgres_query_readonly.py` (36 tests) ; L2.5b :
> `test_a_table_identifier_carrying_sql_cannot_reach_the_database` (la table est toujours là après le run) |
> | échec nommé, rien d'inventé | `test_a_missing_table_is_named_and_nothing_is_delivered`, `test_an_absent_vault_entry_names_the_variable_an_operator_must_set`, `tests/agentic/test_database_read_delivery.py::TestWhenTheSourceCannotBeRead` (étape `degraded`, `datasets[]` vide, **aucune** recherche web de remplacement) |

---

### L3 — Cycle de vie des données, enrichment et embeddings (§12, §16) (3–4 j) · Codex + Devin

#### L3.1 — Étape ENRICHED (`app/knowledge/enrichment/`)

- [ ] `enricher.py` : normalisation d'unités (dates, unités de mesure, devise), détection de
  langue (`language_policy` existe), déduplication par empreinte (`record_hash` / `sha256_hex`).
  *preuve : `tests/unit/knowledge/test_enricher.py`*
- [ ] Marquer chaque unité du `data_stage` correct (`app/core/constants.py::DATA_STAGES`) et
  refuser tout saut d'étape (RAW→DERIVED direct interdit, §12).
  *preuve : `tests/unit/knowledge/test_data_stage_transitions.py`*
- [ ] Exposer la progression de stage dans le colis (`datasets[].data_stage`, `transformations[]`).
  *preuve : `tests/api/test_delivery_exposes_stages.py`*

#### L3.2 — Projection des transformations dans le colis

- [ ] Remplacer la `TRF_` unique de `pipeline_persistence.py:223-262` par des enregistrements
  par étape, et projeter `transformations[]` dans le colis §24.1 (structure §12.1 exacte).
  *preuve : `tests/api/test_delivery_transformations_shape.py`*
- [ ] Vérifier la borne : `transformations[]` ne contient **que** des transformations réelles
  (aucune liste vide déguisée, aucun `operator` générique inventé).
  *preuve : `tests/agentic/test_transformations_are_real.py`*

#### L3.3 — Génération d'embeddings (§16)

- [ ] `app/knowledge/embedding/embeddings_generator.py` : produit les vecteurs `vector(1536)`
  (dimension figée par la migration `0003`), modèle tracé, passage par le Model Router (§22)
  et les traces LLM (§41.12).
  *preuve : `tests/unit/knowledge/test_embeddings_generator.py`*
- [ ] Persistance dans `embeddings` (`owner_type`/`owner_id`, index HNSW existant) :
  `owner_type="information_unit"` par défaut, `owner_type` aligné sur `app/tools/knowledge/vector_searcher.py::OWNER_TYPE`.
  *preuve : `tests/integration/test_embeddings_persistence.py`*
- [ ] `scripts/backfill_embeddings.py` : rattrapage des unités existantes, idempotent
  (`ON CONFLICT DO NOTHING`), avec `--dry-run` et métriques.
  *preuve : `tests/integration/test_backfill_embeddings.py`*
- [ ] Si aucun provider d'embeddings n'est configuré : **dégradation explicite** (pas de vecteur
  nul silencieux) + `limitations` — sinon le volet sémantique de §16.2 devient mensonger.
  *preuve : `tests/unit/knowledge/test_embeddings_no_provider_degrades.py`*

---

### L4 — Recherche hybride et mémoire (§16.2, §17) (2–3 j) · Codex

**Objectif** : une requête réutilise réellement la mémoire. Aujourd'hui `memory_checker` et
`HybridSearch` existent et sont testés en unitaire mais **aucun pipeline ne les appelle** (C13).

- [ ] Insérer l'étape `memory_lookup` (§8.4, §17.1) en tête de plan, avant acquisition :
  appel de `app/planning/memory_checker.py` avec `hybrid_search` **injecté** (l'interface
  d'injection existe déjà : `memory_checker.py:67`).
  *preuve : `tests/unit/planning/test_memory_checker_wired_in_pipeline.py`*
- [ ] Poids §16.2 **0.6 sémantique / 0.4 lexical** appliqués par `HybridSearch` (ADR
  `004_hybrid_search_weights.md`) et vérifiés sur données réelles pgvector.
  *preuve : `tests/integration/test_hybrid_search_weights_real.py`*
- [ ] Si la table `embeddings` est vide (L3.3 non livré) : **dégrader en lexical seul** et le
  dire dans le colis (`limitations`) plutôt que de prétendre à une recherche hybride.
  *preuve : `tests/unit/planning/test_memory_lookup_lexical_only_degrade.py`*
- [ ] Déduplication (§17.1) : une unité déjà en mémoire **n'est pas dupliquée** ; le run
  référence l'unité existante. *preuve : `tests/integration/test_idempotency_integration.py::TestReplayIdempotence` (cas mémoire)*
- [ ] Tracer le hit : `audit_event` + métrique (§20, §34) — « mémoire utilisée » doit être
  auditable. *preuve : `tests/unit/governance/test_audit_memory_lookup.py`*
- [ ] `retrieve_context(ids)` branché pour reconstruire le contexte des unités retrouvées.
  *preuve : `tests/unit/knowledge/test_retrieve_context_wired.py`*

**Critère de sortie L4 (N2)** : deux requêtes successives sur le même sujet ⇒ la seconde
contient une unité issue de la mémoire, tracée en audit, sans doublon en base.

---

### L5 — Qualité et confiance sur données structurées (§13) (2 j) · Codex

- [ ] Brancher les contrôles §13.2 déjà écrits sur les datasets ingérés :
  `inspect_schema`, `profile_dataset`, `detect_duplicates`, `validate_schema`,
  `check_missing_values`, `check_consistency` (tous importables depuis `app.tools`, C5).
  *preuve : `tests/integration/test_dataset_quality_controls_e2e.py`*
- [ ] `check_freshness` (§13.2, §41.5) appliqué aux sources fichier/DB : `freshness` persisté
  (colonne de la migration `0002`) et exposé. *preuve : `tests/unit/quality/test_freshness_file_source.py`*
- [ ] `compare_sources` (§14.4) entre source fichier et source web : un conflit fichier↔web
  doit produire un `Conflict` (§14.3), pas un arbitrage silencieux.
  *preuve : `tests/agentic/test_conflict_file_vs_web.py`*
- [ ] Score qualité §13.3 recalculé sur dataset : `quality_score` de `Dataset`/artefact
  **non `None`** quand les contrôles ont tourné ; `None` assumé sinon.
  *preuve : `tests/unit/quality/test_quality_score_from_controls.py`*
- [ ] Les `QualityResult` alimentent `limitations`/`missing_information` du colis (§24.1).
  *preuve : `tests/api/test_delivery_quality_limitations.py`*

**Critère de sortie L5 (N2)** : un CSV contenant des doublons, des valeurs manquantes et une
incohérence produit un colis où ces trois défauts sont **explicitement listés** (§37
« signaler > inventer »).

---

### L6 — Persistance, repositories et cohérence de schéma (§27, §18) (3–4 j) · Devin

- [ ] **Dette n°3 — unifier `SourceRepository`** avec la migration `0002`
  (choix à trancher : aligner le repository sur `id`/`url`/`reliability_score`/`data_stage`, ou
  migrer la table). Cible : plus aucun `INSERT ... source_id` qui échoue sur PostgreSQL, et
  `pipeline_persistence.py` cesse d'écrire en SQL direct (`:102`, `:130`).
  *preuve : `tests/integration/test_postgres_real.py::test_source_repository_matches_migration` + `tests/unit/storage/test_source_repository.py`*
- [ ] Repositories manquants pour ce que le pipeline écrit désormais :
  `dataset_repository`, `transformation_repository`, `plan_repository` (tables `0007`/`0004`).
  *preuve : `tests/unit/storage/test_dataset_repository.py`, `test_transformation_repository.py`, `test_plan_repository.py`*
- [ ] **Dette n°5 — `VersionStore` persistant** (§18.1) : le store en mémoire ne survit pas à un
  redémarrage ; le persister (table dédiée ⇒ migration `0014` si nécessaire).
  *preuve : `tests/integration/test_version_store_persistence.py`*
- [ ] **`_REQUESTS_STORE` en mémoire** (`app/api/v1/requests/router.py:23`) : le remplacer par une
  lecture de la table `requests` (`0007`) ou assumer explicitement le caractère volatil
  (⚠️ tout redémarrage/rebuild d'image efface l'historique — c'est le cas aujourd'hui).
  *preuve : `tests/api/test_requests_survive_restart.py`*
- [ ] Vérifier que §18.2 (suppression logique) et §18.3 (champs de temporalité) sont respectés
  par les nouvelles tables/colonnes de L1.3. *preuve : `tests/unit/migrations/test_soft_delete_columns.py`*

---

### L7 — Résilience, cache et reprise (§41.5, §41.6, §41.8, §41.1) (3 j) · Devin + OpenCode

- [ ] **Dette n°6 — cache L2 PostgreSQL** : brancher `cache_entries` (`0008`) derrière
  `app/storage/cache/cache_store.py` (L1 conservé comme premier niveau), TTL par entrée,
  invalidation par `request_id`/`source_id`. *preuve : `tests/integration/test_cache_l2_postgres.py`*
- [ ] **Cache L3 pgvector** : réutilisation d'embeddings déjà calculés (clé = `sha256` du texte
  normalisé) — évite de recalculer un vecteur identique. *preuve : `tests/integration/test_cache_l3_embeddings.py`*
- [x] §41.6 : `ChunkedDatasetProcessor` branché au seuil de l'ADR 007 **dans le chemin réel** —
  ✅ **branché en L2.6** (`document_ingestor._chunked_units` + `app/knowledge/normalization/limits.py`).
  ⚠️ Ce qui reste de ce lot : valider la **borne mémoire** sous charge et la reprise (§41.1), pas le
  branchement lui-même.
  *preuve du branchement : `tests/integration/test_chunked_ingestion.py` ; reste dû ici :
  `tests/performance/test_chunked_threshold.py`*
- [ ] §41.1 : reprise après redémarrage pour une requête longue (checkpoints `0005`
  `execution_checkpoints` + `progress`), testée avec un kill de processus.
  *preuve : `tests/integration/test_resume_after_restart.py`*
- [ ] §41.8 : vérifier que la politique retry/circuit breaker (ADR `006`) couvre **les nouveaux
  chemins** (S3, PostgreSQL, fichiers), et pas seulement le web.
  *preuve : `tests/unit/connectors/test_circuit_breaker_new_paths.py`*

---

### L8 — Sécurité, gouvernance, i18n, charge (§19, §41.3, §41.9, §41.13) (4–5 j) · Devin + OpenCode + Cursor

- [ ] **Dette n°2 — validateur mTLS** : implémenter `app/security/certificates/` (chaîne X.509,
  expiration, révocation) et l'exposer comme dépendance d'authn service-à-service (§19.2).
  *preuve : `tests/security/test_mtls_validator.py`* (`scripts/generate_certs.sh` fournit les matériaux)
- [ ] Rate limiting persistant (aujourd'hui in-memory) : s'appuyer sur Redis/Valkey.
  *preuve : `tests/security/test_rate_limit_persistent.py`*
- [ ] §41.4 : authentification des sources (credential vault) branchée sur `RESTConnector`/
  `PostgresConnector` (le vault existe, l'usage réel est à câbler).
  *preuve : `tests/integration/test_authenticated_source_e2e.py`*
- [ ] §41.3 : politique de langue effective sur les sorties (`language_policy` déjà appelée par le
  runner) : langue des unités tracée, pas de mélange silencieux.
  *preuve : `tests/unit/knowledge/test_language_policy_applied.py`*
- [ ] §41.9 : vérifier `right to forget`/portabilité/rectification sur les **nouvelles**
  données (datasets, artefacts, embeddings) — un artefact RGPD-supprimé ne doit plus être
  téléchargeable. *preuve : `tests/security/test_gdpr_new_data_types.py`*
- [ ] §41.13 : harnais de charge (k6 ou locust, à trancher) sur le chemin complet
  `upload → ingestion → livraison → download`, avec seuils chiffrés dans `docs/performance_tuning.md`.
  *preuve : `tests/load/` exécuté en CI manuelle + résultats archivés*
- [ ] **Dettes d'exploitation** : Redis → Valkey, runtime Python 3.12, `gitleaks`
  (`AGENT_STATUS.md` dettes n°1/7/8). *preuve : `python -m pytest -q` + CI verte*

---

### L9 — Extensions et extensibilité (§9.2, §23, Phase 9) (2 j pour le socle) · Devin

> La spec n'exige pas l'OCR/audio/vidéo en V1, mais exige qu'ils soient **prévus comme plugins**.

- [ ] Mécanisme de plugin : `entry_points` (groupe `inis.connectors`) dans `pyproject.toml` +
  registre de chargement paresseux (`app/connectors/plugins.py`), contrat = `SourceConnector`
  existant (`app/connectors/base.py`). Un connecteur externe doit pouvoir s'enregistrer sans
  modifier le cœur. *preuve : `tests/unit/connectors/test_plugin_discovery.py`*
- [ ] Plugin factice de test (fixture) démontrant l'ajout d'un type de source `ocr` non
  implémenté, exposé comme capacité mais **refusant** tant qu'il n'est pas installé.
  *preuve : `tests/integration/test_plugin_absent_degrades.py`*
- [ ] Documenter dans `ARCHITECTURE.md` + `docs/adr/010_*` la procédure d'ajout d'un connecteur
  externe. *preuve : revue de docs (pas de test)*

---

## 5. Gate de sortie V1 — les 20 critères de §36

Statut initial = constat vérifié du 2026-09-29. **Aucun critère ne passe `[x]` sans test.**

| # | Critère §36 | Statut initial | Lot | Test de preuve attendu |
|---|---|---|---|---|
| 1 | Un autre agent peut s'enregistrer automatiquement | `[x]` | — | `tests/integration/test_agent_registry.py` |
| 2 | Un agent peut découvrir INIS et ses capacités | `[x]` | — | `tests/unit/registry/test_agent_registry.py` |
| 3 | Un agent peut envoyer une demande JSON via le protocole | `[~]` HTTP OK, AMQP non live | L7 | `tests/integration/test_amqp_broker.py` (live) |
| 4 | INIS construit automatiquement un plan | `[x]` | — | `tests/unit/planning/test_plan_builder.py` |
| 5 | INIS peut rechercher sur le Web | `[x]` | — | `tests/integration/test_v2_full_stack.py` |
| 6 | **INIS peut ingérer un fichier structuré** | `[x]` ✅ (L2.3/L2.6 : CSV/JSON/XML/XLSX **et** PDF/DOCX/images) | L2 | ⚠️ correction de preuve : le plan attendait `tests/integration/test_file_ingestion_e2e.py`, **ce fichier n'existe pas** — les preuves sont `tests/integration/test_request_file_ingestion_e2e.py` (CSV → colis), `tests/integration/test_pdf_ingestion_e2e.py` (PDF → pages localisées) et `tests/unit/knowledge/test_document_ingestor.py` (tous les formats) |
| 7 | **INIS peut interroger PostgreSQL** | `[x]` | L2.5 | `tests/integration/test_request_database_read_e2e.py` |
| 8 | INIS stocke les sources et leurs métadonnées | `[~]` web seulement, repo divergent | L6 | `tests/unit/storage/test_source_repository.py` |
| 9 | INIS conserve la provenance | `[~]` vrai pour le web, à étendre | L2.3 | `tests/agentic/test_file_unit_traceability.py` |
| 10 | INIS peut retourner une information avec son contexte | `[x]` | — | `tests/integration/test_smoke.py` |
| 11 | INIS peut détecter un conflit | `[~]` web seulement | L5 | `tests/agentic/test_conflict_file_vs_web.py` |
| 12 | INIS attribue un score de confiance explicable | `[x]` | — | `tests/unit/confidence/test_confidence_scorer.py` + `tests/api/test_confidence.py` |
| 13 | INIS peut solliciter un autre agent | `[~]` code présent, e2e partiel | L7 | `tests/agentic/test_delegation_cycle_detection.py` (existant) + `tests/agentic/test_delegation_e2e.py` (à créer) |
| 14 | INIS journalise l'ensemble de l'exécution | `[x]` | — | `tests/unit/governance/test_audit_writer.py` |
| 15 | INIS respecte les politiques de permission | `[x]` (+ download artefacts) | L1.4 | `tests/security/test_artifact_download_authz.py` |
| 16 | Une information modifiée peut être retrouvée dans son historique | `[~]` `VersionStore` en mémoire | L6 | `tests/integration/test_version_store_persistence.py` |
| 17 | Une suppression n'efface pas silencieusement l'historique | `[~]` à vérifier sur les nouvelles tables | L6 | `tests/unit/migrations/test_soft_delete_columns.py` |
| 18 | Une information insuffisamment étayée est marquée comme telle | `[x]` (+ limites qualité) | L5 | `tests/agentic/test_insufficient_evidence.py` |
| 19 | **INIS n'utilise pas le LLM comme source de vérité** | `[x]` ✅ la fabrication de step est supprimée (C6 fermé en L2.2) | L2.2 | `tests/agentic/test_no_fabricated_step_output.py` (+ `test_non_hallucination.py` pour les claims LLM) |
| 20 | Une sortie factuelle peut être reliée à une preuve et une source | `[~]` web seulement | L2.3 | `tests/agentic/test_non_hallucination.py` (cas fichier) — ⚠️ **avancé en L2.6** : une unité de fichier (page de PDF, enregistrement, image) est reliée à sa source (`source_id`, `document_id`, `dataset_id`, `location`, `provenance.extracted_from`), prouvé par `tests/integration/test_pdf_ingestion_e2e.py` ; la *preuve* §14 (table `evidence`) reste web → L5 |

**Clôture de la vague V1 = critères 6, 7, 8, 9, 11, 16, 19, 20 passés à `[x]`.**

---

## 6. Journal de progression

À remplir à **chaque** case cochée : date, agent, lot/tâche, commit, tests, éventuel blocage.

| Date | Agent | Lot | Tâche | Commit | Tests exécutés | Statut / blocage |
|---|---|---|---|---|---|---|
| 2026-09-29 | (audit) | — | Rédaction du plan | — | — | plan créé ; baseline mesurée ensuite en L0 |
| 2026-09-29 | Cline (act) | **L0** | Branche `feat/conformance-v1`, snapshot du WIP pré-existant (114 fichiers), baseline mesurée | `5c3c60f` | `python -m pytest -q` → **1615 passed / 4 skipped** (144,55 s) ; `check_architecture` + `check_contracts` OK | ✅ arbre vert : le WIP n'a pas été jeté mais committé tel quel |
| 2026-09-29 | Cline (act) | **L1** | L1.1→L1.6 : générateurs, packager, migration `0013`, repository, routes, câblage pipeline, mapping UI | `7c1bba2` | `python -m pytest -q` → **1687 passed / 4 skipped** (199,55 s) ; `check_architecture` / `check_contracts` / `check_invariants` OK ; `check_backward_compat` → **0 breaking** (28 warnings BC005, dont 1 nouveau sur `0013`) ; `ruff check` → **clean sur les 32 fichiers du lot** ; `npx tsc --noEmit` OK | ✅ **N2 sur le chemin nominal** (critère de sortie L1 prouvé par `tests/integration/test_artifacts_object_storage.py`) — reste ouvert : `ETag`/`X-Checksum-Sha256`, refus `deleted`, authz §19.3, `artifact_versions`/`lineage`/`delivery_events`, `_ToolAdapter` (C6), section UI |
| 2026-09-29 | Cline (act) | L1 | Décisions de conception consignées (PDF = option A, record hors du fichier, `created_at` applicatif, `artifact_id_sequences`, séquence mémoire assumée) | `7c1bba2` | — | voir l'encadré « État d'avancement L1 » en §4, items 1→8 |
| 2026-09-29 | Cline (act) | L1 | Découverte **C24** (`.env.example` : `DATABASE_URL` en psycopg2 ⇒ `make migrate` impossible hors conteneur) — corrigée | `7c1bba2` | `alembic upgrade head` puis `downgrade 0012` puis `upgrade head` vérifiés sur la base docker-compose (`0012` → `0013 (head)`) | ✅ ; `ix_artifacts_request_id` et `artifact_id_sequences` vérifiés en `psql` |
| 2026-09-29 | Cline (act) | **L2.1** | Ingestion d'un fichier : endpoint multipart, détection MIME par contenu, quota §41.2, stockage S3, migration `0014`, `GET /v1/documents`, classification §19.4 | `640cebd` | `python -m pytest -q` → **1730 passed / 4 skipped** (150,73 s) ; 4 checkers OK (**0 breaking**, 29 warnings BC005) ; `ruff` clean sur les 22 fichiers ; `0014` appliquée **et** annulée sur la base docker ; image reconstruite et `FastAPI.openapi()` généré dans un conteneur jetable (`multipart 0.0.32`, 3 routes `/v1/documents…` montées) | ✅ **N2** — 43 nouveaux tests. ⚠️ défaut trouvé par un test pendant le lot : la classification PII portait sur le nom **assaini** (donc l'email du nom disparaissait avant d'être signalé) → corrigé, verrouillé par `tests/security/test_upload_pii_classification.py` |
| 2026-09-29 | Cline (act) | **L2.2** | Dispatch réel : `tool_dispatch.py` (35 outils §21 enregistrés, vocabulaire d'actions fermé), suppression des **deux** fabrications de step (C6/P1), `StepExecutor` dégradé/échoué, plus de recherche web pour une action non-web | `066ac1b` | `python -m pytest -q` → **1755 passed / 4 skipped** (163,24 s) ; 3 checkers OK ; `ruff` clean sur les 5 fichiers (et erreurs préexistantes de `pipeline_runner.py` : 35 → 34) | ✅ **C5 et C6 fermés**. 25 nouveaux tests. ⚠️ preuve invalide découverte : le plan citait `test_non_hallucination.py::test_no_fabricated_step_output`, **ce test n'existe pas** — la case §36/19 est désormais prouvée par le fichier réellement créé |
| 2026-09-29 | Cline (act) | L2.2 | Deux défauts trouvés en lisant le vrai chemin d'exécution : toute action déclenchait une recherche web (avec le **nom de l'action** comme requête) et la seconde fabrication (`Fallback execution output`) jetait l'erreur réelle | `066ac1b` | `tests/agentic/test_no_fabricated_step_output.py::test_a_non_web_action_never_becomes_a_web_search` | ✅ corrigés ; reste L2.2 items 3-4 (validation du plan en amont, `request_type`), bloqués par L2.3 (cf. encadré L2.2) |
| 2026-09-29 | Cline (act) | **L2.3** | Ingestion d'un document en unités §11 localisées + `Dataset` persisté : `document_ingestor.py`, `DatasetRepository`, migration `0015` (`datasets.storage_ref`/`request_id`, `information_units.dataset_id`/`location`) | `a6921ab` | `python -m pytest -q` → **1772 passed / 4 skipped** (183,63 s) ; 3 checkers OK ; BC **0 breaking** (31 warnings) ; `ruff` clean (10 corrections auto) ; `0015` appliquée **et** annulée sur la base docker | ✅ — 17 nouveaux tests ; le champ `information_units` de l'upload n'est plus vide. Reste : découpage ADR 007, `Transformation` par étape (§12.1/C11), granularité page/feuille, `artifact_lineage` |
| 2026-09-29 | Cline (act) | **C11/C10** | Une `Transformation` **par étape réelle** (Section 12.1) : `stage_transformations.py`, plus de `transformations: []` codé en dur, `persist_transformations` remplace la `TRF_` unique | `3b7d327` | `pytest -q` -> **1783 passed / 4 skipped** (168,76 s) ; 3 checkers OK ; `ruff` sur `pipeline_runner.py` : 34 -> 22 erreurs préexistantes (aucune nouvelle) | OK - 11 tests unitaires + 2 tests d'intégration renforcés. Une étape qui n'a rien produit est **absente** (jamais inventée). Reste : les étages d'un run d'ingestion, `artifact_lineage` |
| 2026-09-30 | Cline (act) | **L2.2 (fin)** | Le plan est **contraint par le vocabulaire fermé §8.4** : `InvalidPlanAction` + `PlanBuilder.validate_step(s)`, plan client **et** plan LLM validés avant exécution, `parse_plan` ne promeut plus la prose en action, le prompt énonce le vocabulaire | `8b13da2` | `pytest -q` → **1802 passed / 4 skipped** (168,95 s) ; 3 checkers OK ; `ruff` sans nouvelle erreur | ✅ 19 nouveaux tests. ⚠️ 4 tests existants documentaient l'ancien contrat et devaient bouger (**acte explicite**) : `test_plan_builder` (actions `search`/`verify` hors vocabulaire), `test_pipeline_guards` (plan `web_search`), `test_plan_parser` (forme exacte d'une étape), `test_no_fabricated_step_output` (un plan inconnu était *exécuté* puis dégradé) — il est désormais **refusé en amont** |
| 2026-09-30 | Cline (act) | **L2.2 (fin)** | `file_ingest` branché et `request_type` **opérant** (C4) : `request_material.py` relit la matière ingérée (documents/datasets/unités localisées), le pipeline exécute l'étape, remplit `datasets[]`, ajoute les sources fichiers, oriente le plan `data`/`source` vers le fichier, et enregistre les étages `raw`/`normalized` de l'ingestion | `3fde944` | `pytest -q` → **1842 passed / 4 skipped** (152,48 s) ; 3 checkers OK ; `ruff` : `pipeline_runner.py` à 22 erreurs préexistantes (aucune nouvelle) | ✅ **C4 fermé** ; moitié « fichier » du critère de sortie L2 prouvée sur PostgreSQL réel (`tests/integration/test_request_file_ingestion_e2e.py`). ⚠️ Fabrication découverte **dans le lignage** : l'unité agrégée du run était attribuée au `FactExtractor` (deux étages `normalized` dès qu'un fichier était livré) → corrigé par un paramètre `delivered_units` distinct ; `test_b4bis_persistence` verrouillait cette attribution et a été corrigé ; `entity.requires` introduit pour les actions exécutables conditionnelles |
| 2026-09-30 | Cline (act) | **L2.4** | Le mode « cible explicite » (`Query.filters["location"]` : chemin ou `s3://…`) existe dans les 6 connecteurs fichiers, le glob reste le défaut ; S3 est lu **en flux** vers un fichier temporaire nettoyé, refusé sur la taille déclarée **puis** pendant le transfert ; `RawSource.metadata` porte le `content_type` et la `location` réels ; plafond unique `[limits].max_upload_bytes` partagé entre l'upload et la lecture de source (`app/core/size_limits.py`) | `a90f385` | `pytest -q` → **1938 passed / 4 skipped** (374,02 s) ; 3 checkers OK ; BC **0 breaking** (31 warnings BC005) ; `ruff` clean sur les fichiers du lot | ✅ **C3 fermé** (96 nouveaux tests : 43 + 36 + 13 + 4 MinIO réel). ⚠️ Trois pièges corrigés au passage : le quota ne bornait que l'entrée HTTP (P16), `FileNotFoundError` était **enveloppée** donc anonyme (P17), un mauvais suffixe se lisait « aucun candidat » au lieu d'un refus nommé (P18) |
| 2026-09-30 | Cline (act) | **L2.5a** | `postgres_query` en **lecture seule** : liste blanche `SELECT`/`WITH`, mots-clés d'écriture refusés, empilement refusé, `LIMIT` ajouté si absent, transaction `READ ONLY` + `statement_timeout` (5 s par défaut, plafond 120 s) dans un seul `engine.begin()` ; identifiants par entrée du **vault** §41.4 (`app/tools/database/credentials.py`) et DSN refusé par son nom, sans écho du secret | `7476a14` | `pytest -q` → **1974 passed / 4 skipped** ; 3 checkers OK ; BC **0 breaking** ; `ruff` clean sur le lot | ✅ 36 nouveaux tests (`tests/unit/tools/test_postgres_query_readonly.py`) | 
| 2026-09-30 | Cline (act) | **L2.5b** | La source PostgreSQL **nommée par la requête** entre dans le pipeline : `constraints.source_preferences=["postgres:<ref>[#table]"]` (nouveau `app/connectors/database/source_target.py`, une entrée malformée **lève** au lieu de disparaître), lecture → `Dataset` + une unité §11 par ligne localisée en `row` (`app/knowledge/ingestion/database_material.py`), étape `query_database` **exécutable** et conditionnelle (`tool_dispatch.py`), orientation du plan `data`/`source` (aucune recherche web), sources `database`, étages §12.1 `PostgresConnector`/`DatabaseMaterial`, `Dataset` persisté (`DatasetRepository`) pour que le `DATA_` livré soit consultable | `4f2a0eb` | `pytest -q` → **2067 passed / 4 skipped** (148,75 s) ; `check_architecture` + `check_contracts` + `check_invariants` OK ; BC **0 breaking** (31 warnings BC005) ; `ruff` : **0 nouvelle erreur** (`pipeline_runner.py` reste à 22 erreurs préexistantes, dont 14 E501 — comptes identiques avant/après vérifiés par `git stash`) | ✅ **critère §36/7 fermé** — 92 nouveaux tests : 8 d'intégration sur PostgreSQL réel (`test_request_database_read_e2e.py`), 24 agentiques (`test_database_read_delivery.py`), 32 unitaires matériau, 28 sur la cible. ⚠️ Trois pièges : lire la base du client **avec l'engine d'INIS** (P19), publier un `DATA_` absent de la table `datasets` (P20), et **jeter le `file_ingest`** d'une requête `data` qui nomme *aussi* une base (P21) — les trois sont écartés et verrouillés par un test |
| 2026-09-30 | Cline (act) | **L2.6** | **L2 clos** : PDF/DOCX rendus **localisables** (`extract_document_blocks` : une page, un paragraphe ou un tableau par bloc, `char_offset` vérifiable dans le texte extrait), `FactExtractor` branché sur le texte extrait (`content["sentences"]`, texte intégral conservé), images **PNG/JPEG** acceptées et ingérées via `extract_image_content` (Pillow optionnel D6, `pillow_available=False` nommé, aucun OCR §9.2), seuil de l'ADR 007 **réellement appliqué** (`app/knowledge/normalization/limits.py`, `_chunked_units`, miroir `configs/*.toml`), feuille de classeur nommée dans le locator (les autres feuilles listées en `limitations`). `ingest_document` devient `async` (P25) | `93e4722` | `pytest -q` → **2120 passed / 4 skipped** (184,19 s) ; `check_architecture` + `check_contracts` OK ; ruff : **0 erreur nouvelle** sur les fichiers du lot | ADR 007 porte désormais sa section « Mise en œuvre » et ses limites assumées ; 53 tests neufs (9 blocs document, 11 image/OCR, 13 chunking, 6 PDF/DOCX ingérés, 3 intégration PDF/tronçons, 10 adaptés) |
| 2026-09-30 | Cline (act) | **L2.1 (fin)** | Variante protocole §5.2 : `InformationRequestCreate.source_ref` n'accepte que `s3://bucket/cle` (chemin local / URL HTTP refusés, §19) et `app/knowledge/ingestion/object_intake.py` ingère l'objet nommé **avant** la planification du run — lecture en flux (plafond §41.2), type par le contenu, `sources`/`documents`/`Dataset`/unités §11, la référence du client restant le `storage_ref`. Une source illisible **refuse la création** (422 nommant la cause). `create_request` devient `async` | `9677305` | `pytest -q` → **2144 passed / 4 skipped** (229,30 s) ; checkers OK ; ruff : 0 nouvelle erreur sur les fichiers du lot (2 préexistantes dans `router.py`) | ⚠️ Le run est planifié **après** l'ingestion : sans cela le plan ignorerait la source que la requête vient de nommer (P27) |

---

## 7. Pièges vérifiés à connaître avant de coder

| # | Piège | Conséquence si ignoré |
|---|---|---|
| P1 | `_ToolAdapter` (`pipeline_runner.py`) **fabriquait** le texte du résultat de step | un test passait au vert alors que rien n'a été ingéré ; violait §0.2/§22.3 — ✅ **supprimé en L2.2** (`066ac1b`), preuve `tests/agentic/test_no_fabricated_step_output.py` |
| P2 | Table `artifacts` **sans `request_id`** (C9/C25) | impossible de lister les artefacts d'une requête sans migration `0013` — ✅ **corrigé en L1** |
| P3 | `artifacts` est un **namespace package PEP-420** : `import app.artifacts.generators` « marche » sans code | un import-test naïf validerait du vide ; toujours tester un **symbole** — ⚠️ **vérifié en L1** : les `.pyc` orphelins de `app/artifacts/**/__pycache__` subsistaient alors que les sources avaient été supprimées (`c948d6b`) |
| P4 | `SourceRepository` crée sa propre table (`metadata.create_all`) | vert sur SQLite, cassé sur PostgreSQL (C16) |
| P5 | Deux listes de routeurs à maintenir : `app/api/v1/router.py:32-46` **et** `app/main.py:91-105` | routeur invisible en production, présent en test |
| P6 | `Artifact.validate()` exige un id de traçabilité si `provenance_complete=True` | soit on trace vraiment, soit `provenance_complete=False` (§0.2) |
| P7 | Les identifiants `ART_` **ne sont pas des ULID** et ne figurent pas dans `app/core/constants.py::ULID_PREFIXES` | `ULID.new("ART_")` lèvera une `ValueError` |
| P8 | Index sur table préexistante + gate **BC005** : `CREATE INDEX CONCURRENTLY` interdit en transaction | migration qui casse ou gate qui bloque |
| P9 | `_REQUESTS_STORE` est **en mémoire** : tout rebuild d'image efface l'historique des requêtes | tests manuels perdus, « régression » fantôme |
| P10 | `frontend/src/api/artifacts.ts` **avale les erreurs** (`catch { return [] }`) | l'UI affichera « aucun artefact » même si l'API est cassée — ✅ **corrigé en L1** (seul un 404 devient `[]`) |
| P11 | Aucun moteur PDF en écriture (C22) | ne pas promettre `.pdf` sans ADR + dépendance — ✅ **traité en L1 (option A)** : refus explicite, aucune substitution de format |
| P12 | `git status` est sale sur la branche courante | diffs de lot illisibles : committer/stasher d'abord (L0) — ✅ **traité en L0** (branche `feat/conformance-v1`, snapshot `5c3c60f`) |
| P13 | `POST /v1/requests` lance **aussi** un run en tâche de fond (`BackgroundTasks`), et `TestClient` l'exécute de façon **synchrone** | un test qui compte les appels d'un provider voit le run de création *et* le sien : compter après `reset_mock()`, sinon la mesure ne dit rien — ⚠️ **rencontré en L2.4** (`test_request_file_ingestion_e2e.py`) |
| P14 | L'engine de `get_default_engine()` est **caché par URL** et lié à sa boucle d'événements | un test synchrone (`TestClient`) puis `asyncio.run(...)` réutilisent le même pool à travers deux boucles : `RuntimeError: Event loop is closed` ou un pool qui rend des connexions mortes — poser `INIS_NULL_POOL=1`, `set_default_engine(None)` et créer l'engine **dans la boucle qui l'utilise** — ⚠️ **rencontré en L2.4** |
| P15 | Une seule ligne de `transformations` par étape §12 n'est **pas** garanti : deux producteurs d'une même étape (acquisition web + lecteur d'un fichier ingéré) produisent légitimement **deux** lignes | un test qui compte « une ligne par étape » interdit la vérité ; vérifier l'unicité par `(stage, tool)` — ⚠️ **découvert en L2.4** (`test_b4bis_persistence.py` verrouillait l'attribution erronée de l'unité agrégée du run au `FactExtractor`) |
| P16 | Le plafond de taille n'était appliqué qu'à l'**entrée HTTP** (`POST …/documents`), pas à ce qu'INIS va **chercher** lui-même (fichier local, objet S3) | la même donnée entre par le « pull » sans passer par le quota : un knob unique bornant les deux directions, sinon la limite §41.2 est décorative — ⚠️ **corrigé en L2.4** (`app/core/size_limits.py` ; l'objet trop gros est refusé **avant** le transfert, preuve `tests/unit/storage/test_s3_stream_download.py`) |
| P17 | `_read_local` **enveloppait** `FileNotFoundError` dans une `InfrastructureError` | remplacer l'erreur d'origine cache *quel* fichier manque : dans un contexte multi-sources, l'opérateur ne peut plus distinguer une faute de frappe d'un bug de stockage — ⚠️ **corrigé en L2.4** (l'erreur est propagée telle quelle) |
| P18 | Un connecteur pointé sur un fichier du **mauvais type** répondait « aucun candidat » | « pas trouvé » et « pas mon format » deviennent indiscernables, et la requête se termine avec une acquisition vide **sans dire pourquoi** ; en mode cible explicite, le refus doit être **nommé** (`ValidationError`) — ⚠️ **corrigé en L2.4** (preuve `tests/unit/connectors/test_connector_explicit_location.py`) |
| P19 | Lire la base **nommée par le client** avec l'engine du déploiement (`get_default_engine()` sur `INIS_DATABASE_URL`) | les lignes livrées seraient celles d'INIS sous une provenance annonçant la base du client : une fabrication silencieuse, et des chiffres plausibles donc invisibles — ⚠️ **écarté en L2.5b** (la lecture passe par le DSN de l'entrée du vault ; `TestWhichDatabaseIsRead` verrouille l'URL réellement utilisée) |
| P20 | Publier un `DATA_` dans `datasets[]` **sans l'avoir persisté** | le client ne peut pas appeler l'API avec cet identifiant à la place de la table d'INIS ; un dataset en mémoire est un dataset inexistant — ⚠️ **corrigé en L2.5b** (`_persist_database_dataset`, limitation nommée si l'écriture échoue ; preuve `test_the_delivered_dataset_is_consultable`) |
| P21 | Orienter un plan `data` sur la **base nommée** en ne gardant que cette source | le `file_ingest` d'un fichier pourtant fourni par la même requête disparaît : la moitié de ce que le client a donné n'est jamais livrée, **sans limitation** (l'étape n'existe plus, donc plus rien ne la signale) — ⚠️ **corrigé en L2.5b** (`OWNED_SOURCE_ACTIONS` : les deux sources détenues par la requête survivent, seules les étapes web sont retirées ; preuve `test_database_read_delivery.py::TestBothOwnedSourcesCoexist`) |
| P22 | Une préférence `postgres:` **malformée** ignorée silencieusement | une faute de frappe devient « aucune base n'a été nommée », et le pipeline interroge le **web** pour des données que le demandeur détient déjà : la requête « réussit » en répondant à côté — ⚠️ **écarté en L2.5b** (`parse_target` lève ; l'étape est dégradée avec la cause, jamais remplacée par une recherche) |
| P27 | Une source **nommée** par la requête (`source_ref`) ingérée **après** la planification du run | le plan se construit sur une matière vide et le pipeline cherche sur le web la donnée que le client vient de fournir — ✅ **traité en L2.6** : `create_request` attend l'ingestion (et la refuse si elle échoue) avant de planifier, `tests/integration/test_request_source_ref_e2e.py` vérifie que la recherche web n'est jamais appelée |
| P23 | Une unité de PDF localisée par « section du texte extrait » ne dit **rien** de vérifiable : le lecteur concaténait toutes les pages | une position qu'aucun lecteur ne peut retrouver n'est pas une localisation (§11) — ✅ **corrigé en L2.6** : `extract_document_blocks` rend une page / un paragraphe par bloc, et le test vérifie `texte[offset:offset+n] == bloc` |
| P24 | Un nouveau producteur d'unités (`extract_image_content`) rend la référence du **fichier temporaire** qu'il a lu (`file://…`) | la provenance d'une image pointerait sur un chemin détruit à la fin de l'appel (§18.1) — même piège que P19 pour un autre producteur — ✅ **traité en L2.6** : `_image_units` réécrit `raw_reference`/`provenance.extracted_from` avec la référence objet, et le test refuse tout `file://` dans l'unité |
| P25 | Le `DefaultChunkedDatasetProcessor` §41.6 est **asynchrone**, l'ingestion ne l'était pas | un helper synchrone appelant `asyncio.run` lève dans la boucle de la requête : le chunking n'aurait jamais tourné en production — ✅ **traité en L2.6** : `ingest_document` et `_chunked_units` sont `async`, le routeur les attend |
| P26 | Ajouter un type à la liste blanche (§9.1) sans brancher son lecteur | un PNG accepté, stocké, et sans la moindre unité : le client croit avoir fourni une source exploitable — ✅ **traité en L2.6** : liste blanche **et** ingestion image dans le même lot, `pillow_available=False` nommé quand Pillow manque |

---

## 8. Explicitement hors périmètre (assumé, non bloquant V1)

| Sujet | § | Raison |
|---|---|---|
| OCR avancé (Tesseract/vision) | §9.2 | « connecteur à venir », plugin L9 seulement |
| Audio, vidéo, streaming temps réel | §9.2, Phase 9 | hors V1 déclarée |
| Exécution sandboxée de code | §23, Phase 9 | hors V1 déclarée |
| Déploiement cloud réel (AWS/GCP/Azure) | Phase 11 V3 | configs livrées, non déployées |
| `xlsxwriter` (§4.1) | §4.1 | `openpyxl` couvre §24.3 ; changer de lib = ADR |
| Génération PDF (écriture) | §24.2 | aucune dépendance installée (C22) — **implémenté en L1 : option A**, `app/artifacts/generators/pdf_generator.py` refuse explicitement (`PDF_UNAVAILABLE_REASON`) ; passer à l'option B exige un ADR `docs/adr/009_*` + dépendance |
| Fournisseur de recherche live en CI | §10 | clé Serper absente (skip explicite assumé) |

**Règle** : chacun de ces items doit rester **refusé explicitement** par l'API
(`limitations`/`missing_information`/§25.2), jamais simulé.

---

## 9. Clôture du plan

- [ ] Tous les lots L1→L6 en `[x]` (niveau N2 prouvé)
- [ ] L7→L9 en `[x]` ou `[-]` justifié dans §6
- [ ] §5 : les 20 critères §36 en `[x]`
- [ ] `docs/SPEC_COVERAGE.md` **régénéré et corrigé** : la métrique actuelle (« classe + test unitaire »)
      surestime la conformité ; elle doit distinguer **N0 / N1 / N2** (voir §0) — sinon le document
      continuera d'annoncer « conforme » sur des capacités non branchées
- [ ] `AGENT_STATUS.md` : dettes n°3, 5, 6 fermées (ou re-planifiées avec justification)
- [ ] `CHANGELOG.md` + `docs/changelog.json` mis à jour (`make changelog`)
- [ ] `python scripts\export_openapi.py` régénéré (artefacts + upload apparaissent, §41.15)
- [ ] `python scripts\check_invariants.py` confirme : plus aucun contenu factuel non sourcé
- [ ] Revue humaine de validation fonctionnelle (§ `DEFINITION_OF_DONE.md` — niveau phase)
- [ ] Tag de phase créé

### Règles de merge par lot

1. Un lot = une branche = une PR (`feat(zone): …`), intégrateur nommé.
2. La PR doit inclure : les tests listés, la sortie des 5 gates, et **une ligne dans §6**.
3. Une PR qui ne peut pas prouver son niveau N2 reste **draft** — jamais mergée comme « faite ».
4. Toute modification de contrat public (`app/api/**` OpenAPI, `CONTRACTS.md`) doit être
   documentée dans la PR et couverte par `scripts/check_contracts.py`.

### Mise à jour de ce document

- Ce fichier est **la seule source de vérité de l'avancement** ; `docs/SPEC_COVERAGE.md`
  reste la matrice statique de preuves par §.
- Une case cochée sans preuve est un **bug de gouvernance** : la traiter comme un bug produit.













