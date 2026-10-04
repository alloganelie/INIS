"""§41.13 — lance une campagne de charge réelle et archive son résultat.

Le scénario, les mesures et les seuils vivent dans ``tests/load/harness.py`` ;
ce module n'est que le point d'entrée opérateur :

    # 1. le système réel (compose) puis l'API
    docker compose up -d postgres object-storage valkey
    uvicorn app.main:app --host 127.0.0.1 --port 8000

    # 2. la campagne
    python -m tests.load.run_load --base-url http://127.0.0.1:8000 \\
        --requests 5 --concurrency 2 --rows 25

Sortie : un résumé lisible sur la sortie standard, et un enregistrement JSON
dans ``tests/load/results/`` (nom = horodatage + commit + verdict). Le code de
sortie vaut ``1`` quand la campagne est en ``FAIL`` : une régression doit casser
la CI manuelle qui l'exécute (``.github/workflows/load.yml``).

La portée ``--scope staging`` applique les seuils exposés par ``/v1/metrics`` ;
``--scope local`` (défaut) les publie sans conclure, parce que §41.13 situe la
mesure en environnement de staging.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

from tests.load.harness import (
    HARNESS_VERSION,
    LoadConfig,
    LoadResult,
    run_load,
    write_result,
)

#: Dossier d'archive par défaut : à côté du harnais, versionné avec lui.
DEFAULT_RESULTS_DIR = Path(__file__).resolve().parent / "results"


def build_parser() -> argparse.ArgumentParser:
    """Return the command line parser of the campaign."""
    parser = argparse.ArgumentParser(
        prog="python -m tests.load.run_load",
        description="§41.13 — campagne de charge sur le chemin réel INIS.",
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--requests", type=int, default=5, help="itérations complètes")
    parser.add_argument("--concurrency", type=int, default=2, help="itérations en parallèle")
    parser.add_argument("--rows", type=int, default=25, help="lignes du jeu de données téléversé")
    parser.add_argument("--format", default="csv", help="format d'artefact demandé")
    parser.add_argument("--timeout", type=float, default=300.0, help="délai d'un appel (s)")
    parser.add_argument(
        "--scope",
        choices=("local", "staging"),
        default="local",
        help="portée de la mesure (§41.13 exige staging pour appliquer les seuils)",
    )
    parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument(
        "--note",
        action="append",
        default=[],
        help="contexte à publier dans le résultat (répétable)",
    )
    return parser


def summarize_for_display(result: LoadResult) -> str:
    """Return the human summary of one campaign (measurements + verdict)."""
    summary: dict[str, Any] = result.summary
    record: dict[str, Any] = result.record
    lines = [
        f"harnais v{HARNESS_VERSION} — {record['git']['commit']} ({record['git']['branch']})",
        f"statut : {result.status}",
        (
            f"requêtes : {summary['requests']} (concurrence {summary['concurrency']}) — "
            f"réussies {summary['ok']}, erreurs {summary['errors']}"
        ),
        (
            f"durée : {summary['duration_s']:.2f} s — débit : "
            f"{summary['throughput_rps']:.3f} parcours/s"
        ),
        "étapes (p50 / p95 / p99 ms, échecs) :",
    ]
    for name, step in summary["steps"].items():
        lines.append(
            f"  {name:18s} {_ms(step['p50_ms'])} / {_ms(step['p95_ms'])} / "
            f"{_ms(step['p99_ms'])} — {step['failed']} échec(s)"
        )
    lines.append("seuils (§41.13, exposés par /v1/metrics) :")
    for check in record["checks"]:
        label = str(check.get("threshold_key") or check["name"])
        lines.append(
            f"  {label:32s} observé={_number(check['observed'])} "
            f"seuil={_number(check['threshold'])} {check['unit']} → {check['status']}"
        )
    if record["limitations"]:
        lines.append("limitations :")
        lines.extend(f"  - {note}" for note in record["limitations"])
    return "\n".join(lines)


def _number(value: Any) -> str:
    """Render a measurement for the console (``—`` when nothing was measured)."""
    if value is None:
        return "—"
    return f"{float(value):.2f}"


def _ms(value: Any) -> str:
    """Render a duration in milliseconds for the console."""
    return _number(value)


async def main(argv: list[str] | None = None) -> int:
    """Run one campaign and archive it; return the process exit code."""
    args = build_parser().parse_args(argv)
    config = LoadConfig(
        base_url=args.base_url,
        requests=args.requests,
        concurrency=args.concurrency,
        timeout_s=args.timeout,
        dataset_rows=args.rows,
        required_format=args.format,
        measurement_scope=args.scope,
        notes=tuple(args.note),
    )

    result = await run_load(config)
    path = write_result(result.record, args.results)
    print(summarize_for_display(result))
    print(f"archive : {path}")
    return 1 if result.status == "FAIL" else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
