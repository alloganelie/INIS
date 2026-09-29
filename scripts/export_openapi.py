"""Exporte le schéma OpenAPI de l'application INIS au format JSON (§41.15).

Usage :
    python scripts/export_openapi.py [chemin_destination]
    # Par défaut : openapi.json à la racine du dépôt
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.main import app  # noqa: E402


def export_openapi(destination: Path) -> None:
    schema = app.openapi()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(schema, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"OpenAPI schema exporté avec succès vers : {destination} ({len(json.dumps(schema))} octets)")


def main() -> int:
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else (ROOT / "openapi.json")
    export_openapi(target)
    return 0


if __name__ == "__main__":
    sys.exit(main())

