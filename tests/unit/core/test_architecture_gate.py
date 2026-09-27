"""§37 / §3 — the architecture rules are enforced, not just documented.

`scripts/check_architecture.py` is the CI gate. This test proves it passes on
the current tree *and* re-checks the underlying rule independently, so a
regression in the script (e.g. an emptied `FORBIDDEN` table) cannot silently
disable the gate.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DOMAIN = ROOT / "app" / "domain"

#: Zone → third-party roots the zone must never import (mirrors the CI gate).
FORBIDDEN_IN_DOMAIN = {
    "sqlalchemy",
    "fastapi",
    "httpx",
    "aio_pika",
    "asyncpg",
    "psycopg",
    "redis",
    "gmqtt",
    "pika",
    "openpyxl",
    "pypdf",
}


def test_architecture_checker_passes_on_the_tree() -> None:
    """`python scripts/check_architecture.py` exits 0 (§37)."""
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_architecture.py")],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_domain_layer_imports_no_io_framework() -> None:
    """`app/domain` stays framework-free — the rule of §37 checked directly."""
    offenders: list[str] = []
    for path in DOMAIN.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots = {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom):
                roots = {(node.module or "").split(".")[0]}
            else:
                continue
            for root in roots & FORBIDDEN_IN_DOMAIN:
                offenders.append(f"{path.relative_to(ROOT).as_posix()}: {root}")

    assert offenders == []
