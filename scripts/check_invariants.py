"""Garde-fous §0.2 — invariants vérifiables exécutables (Phase 8.3).

Heuristiques AST + texte sur ``app/`` (aucun import du projet) :
- inv.8  : aucun finding vérifié sans ``SRC_`` — le split verified/assumptions
           de ``pipeline_runner`` doit filtrer sur ``startswith("SRC_")`` et
           ``evidence_id`` non vide.
- inv.15 : confidence issue de ``app.confidence.confidence_scorer.score``
           avec ``not_a_probability: True``.
- ULID   : les ids créés via ``ULID.new`` portent un préfixe (``XXX_``),
           jamais d'ULID nu.

Usage : ``python scripts/check_invariants.py`` — exit 1 si violation.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
RUNNER = APP / "api" / "v1" / "requests" / "pipeline_runner.py"
SCORER = APP / "confidence" / "confidence_scorer.py"

errors: list[str] = []


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


# -- inv.8 : split verified / assumptions sur SRC_ + evidence ----------------
runner_src = _read(RUNNER)
if 'startswith("SRC_")' not in runner_src and "startswith('SRC_')" not in runner_src:
    errors.append("inv.8: pipeline_runner ne filtre plus les findings sur SRC_")
if "evidence_id" not in runner_src:
    errors.append("inv.8: pipeline_runner ne vérifie plus evidence_id")
if "no_source" not in runner_src or "hypothesis" not in runner_src:
    errors.append("inv.8: claims non sourcées non reléguées en assumptions/hypothesis")

# -- inv.15 : confidence via scorer, not_a_probability ------------------------
scorer_src = _read(SCORER)
if '"not_a_probability": True' not in scorer_src and "'not_a_probability': True" not in scorer_src:
    errors.append("inv.15: confidence_scorer ne marque plus not_a_probability=True")
if "DIMENSION_ORDER" not in scorer_src:
    errors.append("inv.15: scorer découplé des 7 dimensions canoniques (§15.1)")
if "confidence_scorer" not in runner_src and "score_confidence" not in runner_src:
    errors.append("inv.15: pipeline_runner ne passe plus par le scorer §15")

# -- ULID : préfixe obligatoire ------------------------------------------------
bad_ulid: list[str] = []
for py in APP.rglob("*.py"):
    try:
        tree = ast.parse(_read(py), filename=str(py))
    except SyntaxError:
        continue
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            is_ulid_new = (
                isinstance(func, ast.Attribute)
                and func.attr == "new"
                and isinstance(func.value, ast.Name)
                and func.value.id == "ULID"
            )
            if is_ulid_new and not node.args:
                bad_ulid.append(f"{py.relative_to(ROOT)}:{node.lineno}")
if bad_ulid:
    errors.append(f"ULID: ULID.new() sans préfixe: {', '.join(bad_ulid[:5])}")

if errors:
    print("\n".join("ERROR: " + e for e in errors))
    raise SystemExit(1)
print("Invariant checks (§0.2): OK")

