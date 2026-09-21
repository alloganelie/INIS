# PHASE-10 — Résumé factuel (lot 2 : E2E vraie recherche web)

Référence spec : INIS_SPEC.md §0.2 inv.8 (LLM non source de vérité), §9.1 (connecteurs),
§10.1 (recherche web), §10.2 (fiabilité des sources), §11 (InformationUnit), §24 (livraison).
Point d'intégration Cursor : branche `agent/cursor/integration`.
Zone interdite respectée : aucune modification sous `app/`, `pyproject.toml`
(observation en lecture seule + sondages `python -c` / httpx `MockTransport` / ASGI).

## Zones couvertes par ce lot

| Test | Zone observée | État constaté |
|---|---|---|
| `test_wikipedia_provider_imports` | `app.connectors.web.providers.wikipedia_provider` | **présent** : WikipediaProvider (`provider_id="wikipedia"`, OpenSearch, `WIKIPEDIA_SCORE=0.9`) |
| `test_provider_router_fallback_imports` | `app.connectors.web.provider_router` | **présent + repli vérifié** : sans SERPER/BRAVE → `("wikipedia",)` ; ordre SERPER > BRAVE > Wikipedia |
| `test_fact_extractor_imports` | `app.knowledge.extraction.fact_extractor` | **présent** : FactExtractor (1 unité brute/factuelle par phrase) |
| `test_source_reliability_imports` | `app.quality.source_reliability` | **présent** : SourceReliabilityScorer (barème §10.2) |
| `test_wikipedia_provider_smoke` | mapping OpenSearch → SearchResult (httpx `MockTransport`, sans réseau) | **vérifié** : titre/url/provider/score 0.9 |
| `test_fact_extractor_pipeline` | extraction → N unités | **vérifié** : N == phrases (3/3), `INF_*`/`EVID_*`, stage raw, statut factual, provenance `fact_extractor` |
| `test_source_reliability_scoring` | barème sur URLs de test | **vérifié** : gouv 0.95 > wiki 0.85 > media 0.6 > social 0.3 > inconnu 0.5 |
| `test_pipeline_web_search_e2e` | vraie recherche Serper | **skip justifié : `SERPER_API_KEY` absent** (résolution `serper` + search limit=2 si clé présente) |
| `test_pipeline_marks_real_findings` | `PipelineRunner.run` (`app.api.v1.requests.pipeline_runner`, `ModelRouter.complete` mocké) | **vérifié** : finding `SRC_*` + evidence gardé (completed), chaîne brute reléguée en hypothèse |
| `test_pipeline_does_not_use_llm_as_source` | §0.2 inv.8 (`source_id` `llm`/`hypothesis`/absent → hypothèse) | **vérifié** : findings [], `INSUFFICIENT_EVIDENCE`, assumptions `hypothesis/no_source` |

## Tests ajoutés par ce lot

`tests/integration/test_phase_10_e2e.py` : 10 tests, pattern repris des phases 07/09
(`_has_module`, `_has_symbol`, `_import_or_skip`, `_symbol_or_skip`).
Réseau réel uniquement dans `test_pipeline_web_search_e2e` (gardé par clé) ;
Wikipedia est mocké via `httpx.MockTransport`, le LLM via `monkeypatch`
sur `ModelRouter.complete` (réponse `LLMResponse` factice, `stub=False`).
Comportement par défaut de `PipelineRunner.run` sondé : 0,36 s, sans réseau
(ModelRouter en stub), `INSUFFICIENT_EVIDENCE` avec hypothèse unique.
Résultat attendu : 9 passed, 1 skipped (clé Serper absente).

## Statut recherche web

- Chaîne gratuite complète sans clé : Wikipedia (recherche + extraction) → faits → fiabilité.
- Chaîne payante : Serper/Brave sélectionnés par env, non exercés ici (pas de clé).
- Invariant §0.2 appliqué dans `PipelineRunner.run` (lignes ~463-505) : fait vérifié
  ssi `source_id` commence par `SRC_` ET `evidence_id` non vide ; `"hypothesis"`
  rejeté comme source ; chaînes brutes → assumptions.

## Dettes restantes (propriétaires pressentis)

1. Recherche Serper/Brave réelle jamais exercée (pas de `SERPER_API_KEY`/`BRAVE_API_KEY`) — Devin/CI.
2. `WikipediaExtractor` (page → texte) et extracteurs trafilatura/readability non couverts — Devin/Cursor.
3. `app.tools.web.web_search` vide (outil web_search du planner sans implémentation) — Codex/Devin.
4. Persistance faits → `InformationUnit` entité (validation modèle) non exercée, dicts seuls — Codex.
5. Scoring `source_reliability` dupliqué (`app/quality/` vs `app/confidence/dimensions/`) — à unifier — Codex.
6. `MockProvider` (documents fictifs) non asserté ici — Cursor (lot suivant possible).
