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
| C3 | Connecteurs fichiers = `glob("*.csv")` sur un répertoire local | `app/connectors/files/csv_connector.py:22,40,45,60` | §9.1 |
| C4 | `request_type` validé puis **jamais lu** par le pipeline | `schemas.py:70` vs 0 occurrence dans le runner | §1.1, §7 |
| C5 | `ToolRegistry` jamais peuplé ; les 35 outils §21 non adressables | seul `GLOBAL_USAGE.register(...)` | §21 |
| C6 | Le « dispatch » réel est un stub qui **fabrique du texte** | `pipeline_runner.py:1031-1040` (`"Extracted intelligence payload for …"`) | §0.2, §22.3, §37 |
| C7 | `app/artifacts/{delivery,generators,packager}/` + `app/api/v1/artifacts/` = dossiers vides | `dir(app.artifacts.generators) == []`, `git ls-files` vide | §24.2, §24.3 |
| C8 | Aucun ORM/repository `artifact` ; `app/storage/models/` = `account.py` seul | listing | §24.2, §27 |
| C9 | Table `artifacts` (migration `0005:41-58`) **sans `request_id` ni `created_at`** | `migrations/versions/0005_create_remaining_core_tables.py` | §24.2, §32 |
| C10 | Colis §24.1 : `datasets`/`artifacts`/`transformations` **codés en dur à `[]`** | `pipeline_runner.py:1531-1533` | §24.1 |
| C11 | Une **seule** `TRF_` par run, operator générique `PipelineRunner`, jamais projetée | `pipeline_persistence.py:223-262` | §12.1, §24.1 |
| C12 | `app/knowledge/embedding/` et `app/knowledge/enrichment/` vides → `embeddings` jamais alimentée | listing | §12, §16 |
| C13 | `memory_checker`, `HybridSearch`, `VectorSearch`, `ChunkedDatasetProcessor` : **aucun consommateur** | grep global | §16.2, §17, §41.6 |
| C14 | Frontend : `api/artifacts.ts` appelle déjà `GET /artifacts?request_id=` (fallback silencieux) → endpoint absent | `frontend/src/api/artifacts.ts` | §24.2, §31 |
| C15 | `sha256_hex(data)` disponible ; `tests/factories/artifact_factory.py` existe | `app/core/hashing.py:19` | §24.2 |
| C16 | `SourceRepository` divergent de la migration `0002` (`source_id`/`id`) → `INSERT` KO sur PostgreSQL | `AGENT_STATUS.md` dette n°3 | §27, §18 |
| C17 | Cache **L1 seulement** ; `cache_entries` (0008) non câblée | `AGENT_STATUS.md` dette n°6 | §41.5 |
| C18 | `ChunkedDatasetProcessor` présent, **non branché** | `app/knowledge/normalization/chunked_dataset.py` | §41.6 |
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
- [ ] Corriger le chemin stub `_ToolAdapter` (`pipeline_runner.py:1031-1040`, C6) :
  il ne doit plus produire de contenu textuel fabriqué ; s'il est conservé comme
  secours, il doit renvoyer `status="degraded"` **sans** texte prétendant être un résultat.
  *preuve : `tests/agentic/test_non_hallucination.py::test_no_fabricated_step_output` (nouveau cas)*

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
- [ ] Variante protocole : accepter `source_ref: "s3://…"` dans `InformationRequestCreate`
  (`schemas.py:66-87`) pour les agents qui ne font pas de HTTP multipart (§5.2).
  *preuve : `tests/api/test_request_schema_source_ref.py`*

#### L2.2 — Dispatch d'outils réel dans le pipeline (Codex)

> C'est ici que se joue le passage N0 → N1. Aujourd'hui le seul « dispatch » est un stub (C6).

- [ ] `app/agents/pipeline/tool_dispatch.py` : résolveur `action/tool → callable` qui
  **peuple** `ToolRegistry` (`app/tools/registry.py`) avec les outils §21 réellement
  branchables : `read_csv`, `read_excel`, `read_json`, `read_xml`, `read_pdf`,
  `extract_document`, `postgres_query`, `extract_image_content`, `inspect_schema`,
  `profile_dataset`, `detect_duplicates`, `validate_schema`, `check_missing_values`,
  `check_consistency`, `check_freshness`, `compare_sources`, `retrieve_context`, `hybrid_search`.
  *preuve : `tests/unit/agents/pipeline/test_tool_dispatch.py` (chaque nom §21 est résolu ou explicitement listé comme non branchable)*
- [ ] `step_executor.py` : exécuter l'outil résolu et **propager les erreurs** (`InfrastructureError`
  → `status="degraded"` + `limitations`), sans jamais substituer de texte inventé.
  *preuve : `tests/unit/agents/test_step_executor_dispatch.py`*
- [ ] Ajouter au vocabulaire du plan l'action `file_ingest` (§8.4 `file_ingest_step`) :
  `app/planning/plan_builder.py` + `app/planning/step_selector.py` + prompt de planification
  (`app/llm/prompts/planning_prompt.py`) ; le planificateur ne peut proposer que des actions
  présentes dans un **vocabulaire fermé** (défini côté `app/planning/`).
  *preuve : `tests/unit/planning/test_plan_actions_vocabulary.py`*
- [ ] `request_type` devient **opérant** (C4) : `"data"`/`"source"` orientent le plan vers
  `file_ingest`/`postgres_query`. *preuve : `tests/api/test_request_type_routing.py`*

#### L2.3 — Datasets réels et traçabilité (§11, §12, §27)

- [ ] À partir d'un document ingéré, produire un `Dataset`
  (`app/domain/entities/dataset.py` : `dataset_id` `DATA_`, `source_id`, `dataset_schema`,
  `row_count`, `storage_ref`) et le persister dans la table `datasets` (migration `0007`).
  *preuve : `tests/unit/knowledge/test_dataset_from_csv.py` + `tests/integration/test_dataset_persistence.py`*
- [ ] Réutiliser `app/knowledge/normalization/chunked_dataset.py` (déjà écrit, C18) au-delà
  du seuil documenté par l'ADR `007_chunked_processing_threshold.md`.
  *preuve : `tests/integration/test_chunked_ingestion.py`*
- [ ] Unités d'information issues du fichier : **une unité par enregistrement/fragment utile**,
  `type` ∈ {`text`,`table_row`,`document_section`…} selon §11, avec `raw_reference` pointant
  sur `document_id` + `location` (page/feuille/ligne/colonne) — jamais de contenu sans localisation.
  *preuve : `tests/agentic/test_file_unit_traceability.py` (chaque unité est localisable dans le fichier source)*
- [ ] Création d'une `Transformation` **par étape réelle** (§12.1) :
  `RAW → NORMALIZED → ENRICHED → DERIVED`, avec `operator`, `tool`, `tool_version`,
  `parameters`, `result` (remplacer/compléter la `TRF_` unique de `pipeline_persistence.py:223-262`, C11).
  *preuve : `tests/unit/knowledge/test_transformation_records_per_stage.py`*

#### L2.4 — Connecteurs fichiers capables de lire autre chose qu'un répertoire (Devin)

> Aujourd'hui `CSVConnector.discover()` fait `self._base_path.glob("*.csv")` (C3) : un fichier
> uploadé ou un objet S3 est invisible.

- [ ] Ajouter un mode « cible explicite » aux connecteurs (`app/connectors/files/*`) :
  `discover(Query(filters={"location": "s3://…|/abs/path"}))` renvoie exactement ce fichier ;
  conserver le comportement `glob` actuel comme mode par défaut (**non régression** :
  `tests/unit/connectors/test_csv_connector.py` doit rester vert sans modification).
  *preuve : `tests/unit/connectors/test_connector_explicit_location.py`*
- [ ] Téléchargement S3 → répertoire de travail temporaire (`object_downloader`), streaming
  plutôt que `read()` intégral au-delà de `[limits]`.
  *preuve : `tests/integration/test_connector_from_s3.py`*
- [ ] `retrieve()` doit conserver `content_type` + `location` réels dans `RawSource.metadata`
  (indispensable à la localisation §11). *preuve : `tests/unit/connectors/test_raw_source_metadata.py`*

#### L2.5 — PostgreSQL (§36.7) (Devin)

- [ ] Exposer l'outil `postgres_query` **en lecture seule** : liste blanche
  `SELECT`/`WITH`, refus de toute écriture DDL/DML, `LIMIT` forcé, `statement_timeout`,
  connexion par identifiants du **vault** (§41.4, `app/security/vault/credential_vault.py`) —
  **jamais** de DSN dans la requête client.
  *preuve : `tests/unit/tools/test_postgres_query_readonly.py` (SELECT OK ; `UPDATE`/`DROP` refusés)*
- [ ] Étape de plan `database_query` déclenchée par `request_type="data"` +
  `constraints.source_preferences=["postgres:…"]`, résultat converti en `Dataset` + unités
  (même chemin que L2.3). *preuve : `tests/integration/test_postgres_query_e2e.py`*
- [ ] `PostgresConnector` : compléter les méthodes encore stub (`AGENT_STATUS.md`, dette PHASE-11 :
  « read/write encore stub ») ou documenter précisément ce qui reste hors périmètre.
  *preuve : `tests/integration/test_postgres_connector_real.py`*

#### L2.6 — Images et documents non structurés (Codex)

- [ ] Brancher `extract_document` (PDF/DOCX→texte, déjà écrit `app/tools/files/document_reader.py`)
  puis `fact_extractor` sur le texte extrait, avec `location` = page/paragraphe.
  *preuve : `tests/integration/test_pdf_ingestion_e2e.py`*
- [ ] Brancher `extract_image_content` (Pillow) pour les images fournies.
  Pillow est **optionnel par décision D6** (`app/connectors/images/image_connector.py:72-75`):
  quand il est absent, le résultat porte `pillow_available=False` — conserver ce contrat.
  **OCR avancé reste hors périmètre V1** (§9.2) : le comportement par défaut doit être
  « pas d'OCR disponible » + `limitations`, jamais une description inventée.
  *preuve : `tests/unit/tools/test_image_content_no_ocr.py`*

**Critère de sortie L2 (N2)** : un `POST /v1/requests` avec un CSV joint (ou `source_ref`)
produit un colis §24.1 contenant `datasets[]` non vide, des unités localisables dans le fichier,
`transformations[]` non vide, et une provenance complète ; idem avec une requête PostgreSQL
lecture seule ; les tests d'erreur (type refusé, quota, SQL d'écriture) passent.

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
- [ ] §41.6 : `ChunkedDatasetProcessor` branché au seuil de l'ADR 007 **dans le chemin réel**
  (L2.3 le mentionne ; ici on valide la borne mémoire et la reprise).
  *preuve : `tests/performance/test_chunked_threshold.py`*
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
| 6 | **INIS peut ingérer un fichier structuré** | `[ ]` **absent** | L2 | `tests/integration/test_file_ingestion_e2e.py` |
| 7 | **INIS peut interroger PostgreSQL** | `[ ]` **absent** | L2.5 | `tests/integration/test_postgres_query_e2e.py` |
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
| 19 | **INIS n'utilise pas le LLM comme source de vérité** | `[~]` **stub qui fabrique du texte (C6)** | L1.5 | `tests/agentic/test_non_hallucination.py::test_no_fabricated_step_output` |
| 20 | Une sortie factuelle peut être reliée à une preuve et une source | `[~]` web seulement | L2.3 | `tests/agentic/test_non_hallucination.py` (cas fichier) |

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

---

## 7. Pièges vérifiés à connaître avant de coder

| # | Piège | Conséquence si ignoré |
|---|---|---|
| P1 | `_ToolAdapter` (`pipeline_runner.py:1031-1040`) **fabrique** le texte du résultat de step | un test passera au vert alors que rien n'a été ingéré ; viole §0.2/§22.3 |
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













