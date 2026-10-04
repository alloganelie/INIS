# Optimisation, dimensionnement et campagne de charge INIS (§41.13)

§41.13 demande huit benchmarks **nommés**, « **documentés**, **mesurés** en
environnement de staging et **exposés** dans `/v1/metrics` ». La spec **ne fixe
aucun chiffre** : elle nomme les grandeurs et dit où elles doivent vivre. Ce
document recense donc (1) les grandeurs et les valeurs que le système expose déjà,
(2) le harnais qui les mesure sur le chemin réel, (3) comment lancer et archiver
une campagne, et (4) ce qu'une campagne locale ne prouve **pas**.

## 1. Les huit grandeurs du §41.13 et où elles vivent

| §41.13 | valeur exposée | source / mécanisme | mesurée par |
|---|---|---|---|
| `max_plan_steps` | 50 (`MAX_PLAN_STEPS`) | `app/planning/limits.py` : un plan plus long est refusé (`PLANNING_LIMIT_EXCEEDED`) | garde-fou, pas une mesure de charge |
| `max_parallel_tool_calls` | 10 (`MAX_PARALLEL_TOOL_CALLS`) | `app/planning/limits.py::ConcurrencyLimiter` (sémaphore + `peak_active`) | garde-fou, pas une mesure de charge |
| `throughput_requests_per_second` | 50.0 (`target_requests_per_second`) | `GET /v1/metrics → benchmarks` | harnais : parcours **complets réussis** par seconde |
| `vector_search_latency_p99_ms` | 15.0 | idem | `GET /v1/metrics → metrics.vector_search_latency.p99` (§34) |
| `postgres_query_latency_p99_ms` | 5.0 | idem | `GET /v1/metrics → metrics.postgres_latency.p99` (§34) |
| `amqp_message_latency_p99_ms` | 2.0 | idem | `GET /v1/metrics → metrics.broker_latency.p99` (§34) |
| `llm_call_latency_p99_ms` | 500.0 | idem | `GET /v1/metrics → metrics.llm_latency.p99` (§34) |
| `max_information_units_per_request` | au-delà, chunking obligatoire | `app/core/size_limits.py` + traitement par tronçons (§11/ADR 007) | `tests/performance/test_chunked_threshold.py` |

Les valeurs ci-dessus sont celles **du dépôt** (`app/api/v1/system/metrics_router.py`
et `app/planning/limits.py`) ; elles sont publiées telles quelles par
`GET /v1/metrics`. Le harnais les **lit** : il n'en définit aucune, et il n'ajoute
aucun SLA.

## 2. Harnais de charge (§41.13 / plan L8.6)

Le harnais mesure le **système réel** sur le chemin contractuel :

```text
POST /v1/requests                        → support du téléversement
POST /v1/requests/{id}/documents         → upload (multipart, stockage objet, PII)
POST /v1/requests (source_ref=s3://…)    → ingestion avant planification
GET  /v1/requests/{id}                   → attente de la livraison (§1.3)
GET  /v1/artifacts?request_id=…          → artefact demandé (§24.2)
GET  /v1/artifacts/{aid}/download        → octets + sha256 vérifié
```

- code : `tests/load/harness.py` (scénario, mesures, seuils, archive) ;
- point d'entrée opérateur : `python -m tests.load.run_load` ;
- preuves : `tests/load/test_load_harness.py` (structure, parcours réel sur un
  vrai serveur, contre-épreuves) ;
- démonstration rapide des garde-fous : `tests/load/test_benchmarks.py`.

**Choix du pilote — tranché.** Le plan laissait « k6 ou locust ». Le pilote retenu
est **natif Python asyncio**, pour trois raisons vérifiées :

1. le runtime du projet est Python 3.12 : k6 exige un binaire Go supplémentaire et
   un DSL JavaScript hors pile ;
2. Locust 2.46 est **sans support `asyncio`** (pilotage gevent, HTTP uniquement) :
   l'y greffer imposerait deux modèles de concurrence dans un projet async ;
3. le harnais doit produire un **enregistrement déterministe** (commit,
   configuration, mesures, verdict, limitations), ce que le pilote natif fait
   directement.

Un opérateur qui veut un profil de charge différent peut viser les mêmes routes
avec k6 ou Locust : le scénario ci-dessus n'emprunte aucune route créée pour
l'occasion.

## 3. Lancer et archiver une campagne

```bash
# 1. le système réel
docker compose up -d postgres object-storage valkey
alembic upgrade head        # DATABASE_URL pointant vers le PostgreSQL ci-dessus
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# 2. la campagne (portée locale : les seuils sont publiés, pas appliqués)
python -m tests.load.run_load --base-url http://127.0.0.1:8000 \
    --requests 5 --concurrency 2 --rows 25 --note "poste de travail"

# 3. en staging : la même campagne, seuils appliqués
python -m tests.load.run_load --base-url https://inis.staging.internal \
    --requests 50 --concurrency 10 --rows 100 --scope staging
```

Chaque campagne écrit `tests/load/results/<horodatage>-<commit>-<verdict>.json`
(JSON trié : deux campagnes se comparent ligne à ligne). Le code de sortie vaut
`1` en `FAIL`, donc une CI manuelle casse sur une régression de seuil ou de
parcours. Le workflow `.github/workflows/load.yml` (`workflow_dispatch`) exécute
cette campagne et archive le rapport en artefact.

Quand une dépendance externe est neutralisée (fournisseur LLM sans clé en CI),
elle est **déclarée** dans le résultat (`limitations`) : la mesure ne se présente
jamais comme plus complète qu'elle ne l'est.

## 4. Ce qu'une campagne locale ne prouve pas

- Une campagne locale publie les seuils **à côté** des mesures et ne conclut pas :
  §41.13 situe la mesure en staging. Seul un parcours cassé (erreur HTTP, artefact
  absent, `sha256` non vérifié) fait échouer une campagne locale.
- Le verdict porte sur la machine mesurée : un débit de poste de travail n'est pas
  une capacité de production, et l'archive le dit (`environment`, `limitations`).
- Un seuil **sans échantillon** pendant la charge (aucun appel LLM, aucune
  recherche vectorielle) est `not_measured` — jamais un `PASS` de complaisance.

## 5. Niveaux de Cache (§41.5)

- **L1 (In-Memory)** : Cache mémoire local par processus (requêtes web, pages extraites).
- **L2 (Valkey)** : Cache distribué inter-processus et rate limiting (`REDIS_URL`, protocole Redis).
- **L3 (Vectoriel)** : Déduplication sémantique via pgvector.

## 6. Indexation Base de Données
- Index HNSW sur la table `embeddings` (distance cosinus).
- Index GIN sur `information_units.search_vector` pour la recherche lexicale rapide.

