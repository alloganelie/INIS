# Guide de Contribution et Règles de Code

## 1. Respect des Rôles Multi-Agents
Consultez `AGENT_ASSIGNMENTS.md` et `AGENTS.md`. Chaque agent ou développeur doit intervenir uniquement sur ses périmètres assignés.

## 2. Portes de Qualité Obligatoires Avant Tout Commit
Avant de soumettre une modification, lancez impérativement :
```bash
python scripts/check_architecture.py
python scripts/check_contracts.py
python scripts/check_invariants.py
python scripts/check_backward_compat.py migrations/versions/
python -m pytest -q
```

## 3. Règles d'Architecture Clés (§37, CODING_RULES.md)
- Aucun import I/O ou externe dans `app/domain/`.
- Les identifiants doivent être formés via la classe `ULID` typée (`app.domain.value_objects.ulid`).
- Pas d'hallucination silencieuse : le modèle LLM n'est jamais la source de vérité.
- Les migrations de schéma de base de données doivent être rétro-compatibles sans verrouiller les écritures.

