# PHASE-04 — Résumé factuel (lot 1 : intégration + smoke E2E)

Phase active (`agent_workspace/CURRENT_PHASE.md`) : **Information Acquisition — 🚀 EN COURS**.
Référence spec : INIS_SPEC.md §9 (Connecteurs), §10 (Web), §35 (Roadmap Phase 4) ; tests §33.1, §33.2.

Point d'intégration Cursor : branche `agent/cursor/integration`, commit de départ `c9898ca`
(`Merge pull request #14 from alloganelie/agent/antigravity/api`).

## Zones couvertes dans le dépôt à `c9898ca`

| Agent | Zone | Contenu présent |
|---|---|---|
| Codex | `app/domain/entities/` | `source.py` (`Source`), `document.py` (`Document`), `dataset.py` (`Dataset`), `source_candidate.py` (`SourceCandidate`), exportés par `app/domain/entities/__init__.py` |
| Devin | `app/connectors/` | `base.py` (protocole `SourceConnector`, `Query`, `SourceCandidate`, `RawSource`, `SourceMetadata`, `HealthStatus`, `ConnectorMetadata`), `files/` (`CSVConnector`, `JSONConnector`, `ExcelConnector`, + `pdf`, `xml`, `docx`), `database/` (`PostgresConnector`) |
| OpenCode | `app/connectors/api/`, `app/connectors/web/` | `rest_connector.py` (`RESTConnector` + `ApiKeyHandler`, `BasicAuthHandler`, `OAuth2Handler`), `provider_router.py` (`ProviderRouter`, `SearchProvider`, `SearchResult`) + `providers/` (`MockProvider`, `SerperProvider`, `BraveProvider`) |
| Antigravity | `app/api/v1/sources/`, `app/api/v1/information/` | modules `router` exposés via `__init__.py` |
| Cursor (ce lot) | `tests/integration/`, `docs/` | `test_phase_04_e2e.py` (5 smokes d'import/protocole), `test_phase_04_pipeline.py` (cohérence Source→Document + CSV), ce résumé |

## Tests ajoutés par ce lot

`tests/integration/test_phase_04_e2e.py` :

- `test_connectors_import` : import `app.connectors` (`files`, `database`, `api`, `web`)
- `test_domain_entities_import` : import `Source`, `Document`, `Dataset`, `SourceCandidate`
- `test_api_sources_import` : import `app.api.v1.sources` (symbole `router`)
- `test_api_information_import` : import `app.api.v1.information` (symbole `router`)
- `test_source_connector_protocol` : `SourceConnector` est un `Protocol` avec `discover`, `retrieve`, `inspect`, `health_check`, `metadata`

`tests/integration/test_phase_04_pipeline.py` :

- `test_source_to_document` : `Source` + `Document` créés via ULID (`SRC_`, `DOC_`), `document.source_id == source.source_id`, ULIDs valides
- `test_csv_connector_smoke` : `CSVConnector` sur fichier temporaire (`discover` → `retrieve` → `inspect` → `health_check`)

Chaque test skip proprement (`pytest.skip`) si son module est absent. Couverture §33 à ce stade : fumée d'intégration §33.2 limitée aux connecteurs (fichiers) et aux entités ; PostgreSQL, pgvector, object storage, RabbitMQ, MQTT et agent registry restent couverts par les tests existants, sans nouvelle infrastructure dans ce lot.

## Commits PHASE-04 jusqu'à `c9898ca` (historique `git log`)

| Commit | Message |
|---|---|
| `c9898ca` | Merge pull request #14 from alloganelie/agent/antigravity/api |
| `c7ad33a` | feat(api): add /v1/sources and /v1/information endpoints per §32 |
| `a016541` | feat(connectors): add SourceConnector protocol, CSV/JSON/Excel and PostgreSQL connectors per §9 |
| `2abf1b5` | feat(connectors): add REST connector with auth handlers and web provider router per §9, §10 |
| `7f03297` | feat(domain): add Source, Document, Dataset and SourceCandidate entities per §9, §11 |
| `c56fe9c` | docs(phase): close PHASE-03, open PHASE-04 |

## Dettes techniques (à traiter en PHASE-04.2)

1. `Dataset.schema` (`app/domain/entities/dataset.py:11`) masque l'attribut `BaseModel.schema` (warning Pydantic) — à corriger en PHASE-04.2.
2. `SourceConnector` redéclaré localement par OpenCode dans `app/connectors/api/rest_connector.py:32` — convergence vers `app/connectors/base.py` (Devin) à planifier.
3. `SearchResult` + `SearchProvider` définis dans `app/connectors/web/provider_router.py:19,29` — convergence vers domain (Codex) à planifier.
