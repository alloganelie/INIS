"""Point d'entrée principal en ligne de commande pour INIS.

Usage :
    python main.py              # lance l'API uvicorn sur 0.0.0.0:8000
    python main.py --help       # affiche les options disponibles
"""

from __future__ import annotations

import argparse
import os
import sys

import uvicorn


def parse_args(args: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="INIS — Intelligent Networked Information System"
    )
    parser.add_argument(
        "--host",
        default=os.getenv("HOST", "0.0.0.0"),
        help="Hôte d'écoute (défaut : 0.0.0.0 ou $HOST)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("PORT", "8000")),
        help="Port d'écoute (défaut : 8000 ou $PORT)",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        default=os.getenv("ENVIRONMENT", "development").lower() == "development",
        help="Activer le rechargement automatique en dev",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=int(os.getenv("WEB_CONCURRENCY", "1")),
        help="Nombre de processus workers (défaut : 1)",
    )
    return parser.parse_args(args)


def main() -> int:
    args = parse_args()
    # En mode reload, uvicorn attend un import string plutôt qu'un objet instance
    app_target = "app.main:app"
    uvicorn.run(
        app_target,
        host=args.host,
        port=args.port,
        reload=args.reload,
        workers=args.workers if not args.reload else 1,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

