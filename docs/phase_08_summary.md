# PHASE-08 — Résumé factuel (lot 1 : E2E frontend)

Référence spec : INIS_SPEC.md §31 (frontend minimal, 9 écrans §31.1, écran de confiance §31.2).
Point d'intégration Cursor : branche `agent/cursor/integration`.
Zone observée en lecture seule : `frontend/` (+ `docker/` pour les fichiers Docker).
Zone interdite respectée : aucune modification sous `frontend/`, `app/`, `pyproject.toml`.

## Zones couvertes par ce lot

| Test | Zone observée | État constaté |
|---|---|---|
| `test_frontend_config_exists` | `frontend/package.json`, `vite.config.ts`, `tsconfig.json`, `index.html` | **présents, non vides** |
| `test_frontend_9_pages_exist` | `frontend/src/pages/*.tsx` (9 écrans §31.1) | **9/9 présents** : SubmitRequest, RequestStatus, Sources, ConfidenceMatrix, Conflicts, InformationUnits, AgentsSolicited, Traceability, RequestHistory |
| `test_frontend_components_exist` | `frontend/src/components/*.tsx` | **6/6 présents** : AgentCard, ConfidenceBar, ConflictCard, EpistemicBadge, Layout, ProgressStepper (+ ProvenanceTree en bonus, voir dettes) |
| `test_frontend_api_clients_exist` | `frontend/src/api/*.ts` | **10/10 présents** : agents, artifacts, auth, conflicts, evidence, information, quality, requests, sources + client.ts |
| `test_frontend_types_exists` | `frontend/src/types/*.ts` | **4/4 présents** : domain, api, protocol, index |
| `test_frontend_mocks_exists` | `frontend/src/mocks/*.ts` | **3/3 présents** : fixtures, server, browser (MSW) |
| `test_frontend_docker_exists` | Docker frontend | **présents sous `docker/`** : Dockerfile.frontend, docker-compose.frontend.yml (pas sous `frontend/`) |
| `test_frontend_contexts_exists` | `frontend/src/contexts/*.tsx` | **2/2 présents** : AuthContext (AuthProvider, login/logout/refresh), TraceContext (TraceProvider, traceId `TRC_*`) |
| `test_frontend_hooks_exists` | `frontend/src/hooks/*.ts` | **3/3 présents** : useRequest, useSSE, useConfidence |
| `test_frontend_buildable` | `npm run build` (`tsc && vite build`) | **skip justifié : `frontend/node_modules` absent** dans cet environnement |

## Tests ajoutés par ce lot

`tests/integration/test_phase_08_e2e.py` : 10 tests, pattern existence avec skip propre
(helpers `_has_file` — fichier régulier non vide, `_has_dir`, `_list_files`,
`_require_files` qui skippe en listant chaque fichier manquant).
Aucun serveur requis ; seul `test_frontend_buildable` exécute un sous-processus
(`npm run build`, timeout 600 s) et uniquement si `node_modules` est présent.
Résultat attendu : 9 passed, 1 skipped (build, `node_modules` absent).

## Statut build

- Non vérifié ici : `node_modules` absent, `npm run build` non exécuté (skip explicite).
- `package.json` : scripts `dev` (vite), `build` (`tsc && vite build`), `preview`, `test` (vitest) ;
  dépendances React 18, react-router-dom 6, axios, MSW, vitest.
- Fichiers relevés mais hors périmètre de ce lot : `src/App.tsx`, `src/main.tsx`,
  `src/App.test.tsx`, `src/styles/`, `src/mocks/README.md`.

## Dettes restantes (propriétaires pressentis)

1. Build frontend jamais exécuté en CI locale (pas de `node_modules`) — Antigravity/CI.
2. `ProvenanceTree.tsx` (7e composant) hors liste des 6 testés — à rattacher au §31 ou à la traçabilité (§8) — Antigravity.
3. Fichiers Docker sous `docker/` et non `frontend/` — convention à confirmer — Devin/Antigravity.
4. Aucun test navigateur E2E (Playwright/Cypress) — seuls les mocks MSW + `App.test.tsx` (vitest) existent — Antigravity/Cursor.
5. Couverture vitest (`npm test`) non assertée par ce lot — Cursor (lot suivant possible).
6. Adéquation des 9 pages au §31.2 (matrice 7 dimensions) et aux contrats §32 non vérifiée ici (structure seule) — Antigravity.
