"""§16.1 — rattraper les embeddings des unités §11 déjà stockées.

L'index ``embeddings`` (migration ``0003``, HNSW cosinus) est lu par
``app/tools/knowledge/vector_searcher.py`` : sans ce rattrapage, toutes les
unités écrites **avant** L3.3 resteraient invisibles pour §16.2.

Usage ::

    python scripts/backfill_embeddings.py --dry-run
    python scripts/backfill_embeddings.py --limit 500 --report backfill.json
    python scripts/backfill_embeddings.py --request-id REQ_01… --model text-embedding-3-small

Propriétés :

* **idempotent** — les unités qui ont déjà un vecteur ne sont pas relues
  (``LEFT JOIN … IS NULL``) et l'écriture est ``ON CONFLICT (embedding_id) DO
  NOTHING`` : relancer le script ne duplique jamais un vecteur ;
* **``--dry-run``** — énumère exactement ce qui serait vectorisé, n'appelle
  aucun modèle et n'écrit rien ;
* **métriques** — le rapport JSON (stdout, et ``--report``) porte les compteurs
  du lot : candidats, vecteurs produits, lignes insérées, unités écartées et
  limitations. Aucune métrique §34 n'est inventée pour l'occasion ;
* **dégradation explicite** — sans ``LLM_API_KEY`` aucun vecteur n'est produit
  (jamais de vecteur nul) et le rapport nomme la variable manquante ; sans
  ``INIS_DATABASE_URL`` le script s'arrête en le disant (code de sortie 2).

Codes de sortie : ``0`` tout s'est fait, ``1`` dégradé (voir ``limitations``),
``2`` rien n'a pu être tenté (base non configurée).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.knowledge.embedding import (
    EMBEDDING_DIMENSION,
    EMBEDDING_OWNER_TYPE,
    generate_embeddings,
    persist_embeddings,
)
from app.llm.router.model_router import ModelRouter
from app.llm.tracing.llm_trace_writer import LLMTraceWriter
from app.storage.database.engine import (
    create_engine_or_none,
    get_default_engine,
)
from app.storage.repositories.embedding_repository import (
    DEFAULT_DATA_STAGES,
    EmbeddingRepository,
)

EXIT_OK = 0
EXIT_DEGRADED = 1
EXIT_NOTHING_TRIED = 2


def build_parser() -> argparse.ArgumentParser:
    """Return the command-line parser of the backfill."""
    parser = argparse.ArgumentParser(
        description="Rattrape les embeddings §16.1 des unités §11 déjà stockées.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="énumère les candidats sans appeler de modèle et sans écrire",
    )
    parser.add_argument("--limit", type=int, default=200, help="unités maximum par lot")
    parser.add_argument("--batch-size", type=int, default=None, help="textes par appel")
    parser.add_argument("--request-id", default=None, help="restreindre à une demande")
    parser.add_argument("--owner-type", default=EMBEDDING_OWNER_TYPE)
    parser.add_argument(
        "--data-stages",
        default=",".join(DEFAULT_DATA_STAGES),
        help="stades §12 à vectoriser (défaut : normalized,enriched,derived)",
    )
    parser.add_argument("--model", default=None, help="modèle d'embeddings à utiliser")
    parser.add_argument("--dsn", default=None, help="URL PostgreSQL (défaut : INIS_DATABASE_URL)")
    parser.add_argument("--report", default=None, help="écrit le rapport JSON à ce chemin")
    return parser


def _stages(value: str) -> list[str]:
    """Return the §12 stages named on the command line, in order."""
    return [stage.strip() for stage in str(value or "").split(",") if stage.strip()]


def _report(payload: dict[str, Any], path: str | None) -> None:
    """Print the JSON report and, when asked, write it to *path*."""
    document = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    print(document)
    if path:
        Path(path).write_text(document + "\n", encoding="utf-8")


async def _run(args: argparse.Namespace) -> int:
    """Enumerate the missing vectors, produce them, persist them, report."""
    started = time.perf_counter()
    report: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "dry_run": bool(args.dry_run),
        "owner_type": args.owner_type,
        "data_stages": _stages(args.data_stages),
        "dimension": EMBEDDING_DIMENSION,
        "candidates": 0,
        "embedded": 0,
        "persisted": 0,
        "skipped": [],
        "limitations": [],
        "traces": {"built": 0, "persisted": False},
    }

    engine = create_engine_or_none(args.dsn) if args.dsn else get_default_engine()
    if engine is None:
        return _fail(
            report,
            args.report,
            "Aucune base configurée (INIS_DATABASE_URL ou --dsn) : le rattrapage "
            "n'a rien pu énumérer (§16.1).",
        )

    try:
        units = await EmbeddingRepository.list_units_without_embedding(
            engine,
            owner_type=args.owner_type,
            limit=max(1, int(args.limit)),
            request_id=args.request_id,
            data_stages=_stages(args.data_stages),
        )
    except Exception as exc:  # noqa: BLE001 - §25.2 : la cause est nommée
        return _fail(
            report,
            args.report,
            f"Lecture des unités sans vecteur impossible ({type(exc).__name__}: {exc}).",
        )

    report["candidates"] = len(units)
    report["candidate_ids"] = [str(unit.get("information_id")) for unit in units]
    if args.dry_run:
        report["dry_run_note"] = (
            "Aucun modèle n'a été appelé et aucune ligne n'a été écrite : ce rapport "
            "est la liste exacte de ce qui serait vectorisé."
        )
        report["duration_seconds"] = round(time.perf_counter() - started, 3)
        _report(report, args.report)
        return EXIT_OK if units else EXIT_DEGRADED

    if not units:
        report["limitations"].append(
            "Aucune unité §11 sans vecteur : l'index est déjà à jour (§16.1)."
        )
        report["duration_seconds"] = round(time.perf_counter() - started, 3)
        _report(report, args.report)
        return EXIT_OK

    trace_writer = LLMTraceWriter()
    outcome = await generate_embeddings(
        units,
        router=ModelRouter(),
        model=args.model,
        batch_size=args.batch_size,
        trace_writer=trace_writer,
        request_id=args.request_id,
        step_id="backfill_embeddings",
    )
    report["model"] = outcome.model
    report["embedded"] = outcome.vector_count
    report["skipped"] = [dict(item) for item in outcome.skipped]
    report["limitations"].extend(outcome.limitations)
    report["traces"]["built"] = len(trace_writer.list_traces())

    if not outcome.records:
        report["duration_seconds"] = round(time.perf_counter() - started, 3)
        _report(report, args.report)
        return EXIT_DEGRADED

    written, persistence_limits = await persist_embeddings(outcome.records, engine=engine)
    report["persisted"] = written
    report["limitations"].extend(persistence_limits)
    report["duration_seconds"] = round(time.perf_counter() - started, 3)
    _report(report, args.report)
    return EXIT_DEGRADED if report["limitations"] else EXIT_OK


def _fail(report: dict[str, Any], path: str | None, message: str) -> int:
    """Report a run that could not even start, and return its exit code."""
    report["limitations"].append(message)
    _report(report, path)
    return EXIT_NOTHING_TRIED


def main(argv: list[str] | None = None) -> int:
    """Entry point of ``scripts/backfill_embeddings.py``."""
    args = build_parser().parse_args(argv)
    if not os.environ.get("LLM_API_KEY") and not args.dry_run:
        # Stated before any call: the report will carry it as a limitation.
        print(
            "Note : LLM_API_KEY absent — aucun vecteur ne sera produit "
            "(aucun vecteur nul n'est inventé, §0.2).",
            file=sys.stderr,
        )
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
