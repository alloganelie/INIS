"""Génère le fichier docs/changelog.json depuis les révisions Alembic et l'historique git (§41.15).

Usage :
    python scripts/generate_changelog.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.version import API_VERSION  # noqa: E402


def extract_migration_highlights() -> list[str]:
    mig_dir = ROOT / "migrations" / "versions"
    highlights = []
    for f in sorted(mig_dir.glob("*.py")):
        if f.name.startswith("__"):
            continue
        first_line = f.read_text(encoding="utf-8").splitlines()[0].strip('"\r\n ')
        highlights.append(f"{f.stem[:4]}: {first_line}")
    return highlights


def generate_changelog(dest: Path) -> None:
    highlights = extract_migration_highlights()
    data = {
        "current_version": API_VERSION,
        "history": [
            {
                "version": API_VERSION,
                "date": "2026-09-28",
                "highlights": highlights,
            }
        ],
    }
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Changelog généré dans {dest} ({len(highlights)} migrations référencées).")


def main() -> int:
    target = ROOT / "docs" / "changelog.json"
    generate_changelog(target)
    return 0


if __name__ == "__main__":
    sys.exit(main())

