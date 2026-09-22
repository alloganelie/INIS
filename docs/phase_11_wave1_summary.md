# PHASE-11 — Résumé factuel (vague 1 : E2E comptes + connecteurs + cloud)

Point d'intégration Cursor : branche `agent/cursor/integration`.
Zone interdite respectée : aucune modification sous `app/`, `pyproject.toml`
(observation en lecture seule : glob, grep, `python -c`, `docker version`).

## Zones couvertes par ce lot

| Test | Zone observée | État constaté |
|---|---|---|
| `test_account_entity_imports` | `app/domain/entities/account` | **skip : module absent** (41 entités listées, aucune `account`) |
| `test_session_entity_imports` | `app/domain/entities/session` | **skip : module absent** (`app/storage/database/session.py` n'est qu'une fabrique SQLAlchemy, pas une entité) |
| `test_email_vo_validates` | `app/domain/value_objects/email` | **skip : module absent** (12 VO listés, aucun `email` ; seul motif email connu : regex PII) |
| `test_account_repository_imports` | `app.storage.repositories.account_repository` | **skip : module absent** (19 repositories listés, aucun `account`/`session`) |
| `test_session_repository_imports` | `app.storage.repositories.session_repository` | **skip : module absent** |
| `test_s3_client_imports` | `app.storage.object_storage.s3_client` | **skip : module présent mais vide (0 octet)**, comme tout `object_storage/` |
| `test_xml_connector_imports` | `app.connectors.files.xml_connector` | **skip : fichier présent mais vide (0 octet)** |
| `test_docx_connector_imports` | `app.connectors.files.docx_connector` | **skip : fichier présent mais vide (0 octet)** |
| `test_rss_connector_imports` | `app.connectors.files/rss` + `web/rss` | **skip : modules absents** (connecteurs fichiers : csv, docx, excel, json, pdf, xml) |
| `test_password_hasher_imports` | `app.core.hashing`, `app.security.authn.password_hasher` | **skip : `hashing.py` vide, aucun hasher** (authn : jwt, api_key, mtls seuls ; ni passlib/bcrypt dans `app/`) |
| `test_accounts_endpoint_register` | POST `/v1/accounts/register` | **skip : endpoint absent** (routers v1 : agents, artifacts, auth, confidence, conflicts, evidence, information, quality, requests, sources, system) |
| `test_accounts_endpoint_login` | POST `/v1/accounts/login` | **skip : endpoint absent** (auth mock `USERS_DB` en mémoire, pas de comptes persistés) |
| `test_password_hash_verify_roundtrip` | roundtrip hash/vérification | **skip : hasher absent, aucun roundtrip vérifiable** (refus d'inventer un contrat stdlib) |
| `test_cloud_configs_exist` | `deploy/cloud/` | **skip : répertoire absent** (`deploy/` = helm + k8s + README seuls) |
| `test_migration_0006_upgrade` | `migrations/versions/*0006*` + Docker | **skip : migration 0006 absente** (0001-0005 seuls ; de plus daemon Docker injoignable : `docker version` client 29.7.2, npipe manquant) |

## Tests ajoutés par ce lot

`tests/integration/test_phase_11_wave1_e2e.py` : 15 tests baseline, pattern repris
des phases 07/09/10 (`_has_module`, `_has_symbol`, `_import_or_skip`,
`_require_any_symbol`) + `_require_files` (configs) ; HTTP via `httpx.ASGITransport`
si un router comptes apparaît ; migration 0006 gardée par fichier PUIS daemon Docker
(`docker info`, timeout 30 s). Résultat attendu : 0 passed, 15 skipped, motifs explicites.

## Statut vague 1

- Baseline posée : chaque absence est nommée (module, symbole ou fichier + taille 0 octet).
- Aucun test vert à ce stade : les zones comptes/connecteurs-fichiers/cloud sont
  à construire (ou à cadrer comme hors périmètre) par les rôles propriétaires.

## Dettes restantes (propriétaires pressentis)

1. Entités `Account`/`Session` + VO `Email` — Codex (domaine).
2. Repositories comptes/sessions — Devin (storage).
3. `app/storage/object_storage/` vide (s3_client, uploader, downloader) — Devin.
4. Connecteurs `xml`/`docx` vides, `rss` inexistant — Devin.
5. Hachage mot de passe (`app/core/hashing.py` vide) + endpoints `/v1/accounts/*` — Antigravity/Codex.
6. `deploy/cloud/` inexistant (helm/k8s seuls) — Devin.
7. Migration 0006 inexistante ; daemon Docker indisponible dans cet env — Devin/CI.
