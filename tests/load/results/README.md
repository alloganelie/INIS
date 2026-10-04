# Résultats de campagne de charge (§41.13)

Ce dossier contient les **enregistrements de campagne** produits par
`python -m tests.load.run_load` (ou par la CI manuelle
`.github/workflows/load.yml`, qui les publie aussi en artefact).

## Règle

Un fichier de ce dossier est une **mesure réelle** d'un environnement nommé : il
n'est jamais fabriqué, jamais retouché, et jamais présenté comme une capacité de
production. Si aucun résultat n'a encore été obtenu pour une configuration, on
n'écrit pas de chiffre : on documente la procédure.

## Nom d'un enregistrement

```text
<horodatage UTC>-<commit court>-<MEASURED|PASS|FAIL>.json
exemple : 20261004T175737Z-db16d9a-MEASURED.json
```

## Ce qu'un enregistrement contient

| champ | contenu |
|---|---|
| `harness_version` | version du harnais **et** du schéma de résultat |
| `git` | commit, branche, arbre sale ou non au moment de la mesure |
| `environment` | version de Python, plateforme, nombre de CPU |
| `config` | `base_url`, requêtes, concurrence, lignes du jeu de données, format demandé, portée |
| `scenario` | les six étapes réellement appelées |
| `metrics` | requêtes, succès, erreurs, taux d'erreur, durée, débit, p50/p95/p99 par étape |
| `thresholds` | seuils **lus** dans `GET /v1/metrics → benchmarks` (§41.13) + garde-fous |
| `checks` | par seuil : observé, seuil, unité, verdict (`pass`/`fail`/`not_measured`), raison |
| `status` | `PASS` (seuils appliqués et tenus), `FAIL` (seuil dépassé ou parcours cassé), `MEASURED` (portée locale : rien à conclure) |
| `limitations` | ce qui a été neutralisé, ce qui n'est pas comparable, et pourquoi |

## Enregistrement archivé

`20261004T175737Z-db16d9a-MEASURED.json` — campagne réelle obtenue par

```bash
python -m pytest tests/load/test_load_harness.py::test_the_harness_drives_the_real_path_over_http --basetemp=.load_temp
```

Contexte exact (il est aussi dans le fichier) : commit `db16d9a` + le lot L8.6 en
cours dans l'arbre de travail (donc `git.dirty = true`), 2 parcours complets, 2 en
parallèle, jeu de données de 5 lignes, portée `local`.

- **réel** : serveur uvicorn sur socket TCP, routes de l'application, PostgreSQL
  pgvector réel, stockage objet S3 réel, vérification du `sha256` de l'artefact
  téléchargé ;
- **neutralisé et déclaré** : le fournisseur LLM, simulé par la suite
  (`mock_llm`) — la valeur est écrite dans `limitations`, et `llm_latency`
  provient des appels simulés ;
- **non comparable** : cette machine (Python 3.11, 8 CPU, services locaux) n'est
  pas un environnement de staging, donc les seuils sont publiés mais non
  appliqués (`checks[].status = not_measured`).
