"""Rollback interactif d'une ou plusieurs migrations Alembic (§41.14).

Usage :
    python scripts/migrate_rollback.py [étapes] [--yes]
"""

from __future__ import annotations

import argparse
import subprocess
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Rollback sécurisé des migrations Alembic")
    parser.add_argument("steps", nargs="?", default="1", help="Nombre d'étapes de rollback (défaut : 1)")
    parser.add_argument("-y", "--yes", action="store_true", help="Confirmer sans invite interactive")
    args = parser.parse_args()

    steps = int(args.steps)
    target = f"-{steps}"

    if not args.yes:
        try:
            confirm = input(f"Confirmer le rollback de {steps} migration(s) vers '{target}' ? (o/N) ")
            if confirm.lower() not in ("o", "oui", "y", "yes"):
                print("Opération annulée.")
                return 0
        except (EOFError, KeyboardInterrupt):
            print("\nOpération annulée.")
            return 0

    print(f"Exécution : alembic downgrade {target}...")
    res = subprocess.run([sys.executable, "-m", "alembic", "downgrade", target])
    return res.returncode


if __name__ == "__main__":
    sys.exit(main())

