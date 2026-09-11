from __future__ import annotations
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"

FORBIDDEN = {
    "domain": {"sqlalchemy","fastapi","httpx","aio_pika","asyncpg","psycopg","redis","gmqtt","pika","openpyxl","pypdf"},
}

def imported_root(node):
    if isinstance(node, ast.Import):
        return node.names[0].name.split(".")[0]
    if isinstance(node, ast.ImportFrom):
        return (node.module or "").split(".")[0]
    return None

errors = []
for py in APP.rglob("*.py"):
    rel = py.relative_to(APP).as_posix()
    zone = rel.split("/")[0]
    rules = FORBIDDEN.get(zone)
    if not rules:
        continue
    try:
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
    except SyntaxError as exc:
        errors.append(f"{rel}: {exc}")
        continue
    for node in ast.walk(tree):
        name = imported_root(node)
        if name in rules:
            errors.append(f"{rel}: forbidden dependency '{name}'")

for py in APP.rglob("*.py"):
    if "vector(1536)" in py.read_text(encoding="utf-8", errors="ignore"):
        errors.append(f"{py.relative_to(ROOT)}: hard-coded vector(1536)")

if errors:
    print("\n".join("ERROR: " + x for x in errors))
    raise SystemExit(1)
print("Architecture checks: OK")
