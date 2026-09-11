from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
errors = []

# Dossiers de code obligatoires
for rel in ["app", "migrations", "tests"]:
    if not (ROOT / rel).exists():
        errors.append("missing: " + rel)

# Documents de gouvernance à la racine (déplacés depuis inis_governance_docs/)
for doc in ["AGENT_RULES.md", "ARCHITECTURE.md", "INIS_SPEC.md", "CONTRACTS.md"]:
    if not (ROOT / doc).exists():
        errors.append("missing doc: " + doc)

paths = list((ROOT / "app").rglob("*.py"))
all_text = "\n".join(p.read_text(encoding="utf-8", errors="ignore") for p in paths)

if "InformationPackage" not in all_text:
    errors.append("InformationPackage contract not detected")

if "provenance" not in all_text.lower():
    print("WARNING: provenance contract not detected by heuristic")

if errors:
    print("\n".join("ERROR: " + x for x in errors))
    raise SystemExit(1)

print("Contract checks: OK")
