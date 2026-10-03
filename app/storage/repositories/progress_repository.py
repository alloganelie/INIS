"""§41.1 — la progression d'une requête, persistée dans ``progress``.

Le contrat est explicite : « Le demandeur DOIT pouvoir interroger la progression
**sans attendre la livraison finale** », sur ``GET /v1/requests/{id}/progress``,
avec ``steps_total``, ``steps_done``, ``current_step``, ``estimated_completion``
et ``partial_findings_available``. La table ``progress`` (révision ``0005``) porte
exactement ces colonnes — et **rien ne l'écrivait** : la progression vivait dans
le ``RequestLifecycle`` en mémoire, donc un redémarrage du worker la faisait
disparaître alors que la requête, elle, restait en base.

Ce module ne duplique pas la logique de point de reprise (§41.1) : il écrit une
**projection de progression** au même moment que le point de reprise, et lit la
dernière projection connue. La cohérence est celle des données, pas d'une seconde
machine à états :

* ``steps_done`` est le nombre d'étapes **réellement committées** ;
* ``steps_total`` est le total du plan de ce run ;
* ``current_step`` est l'étape en cours, ou ``DELIVERY`` quand le run est fini ;
* un run terminé (point de reprise non reprenable) **ne peut pas** apparaître en
  cours : c'est la ligne de ``execution_checkpoints`` qui fait foi, et elle est
  écrite par le même appel.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    MetaData,
    Table,
    Text,
    select,
)

from app.storage.repositories.table_repository import (
    TableRepository,
    as_iso,
    insert_statement,
)

__all__ = ["ProgressRepository", "progress_table"]

progress_metadata = MetaData()

progress_table = Table(
    "progress",
    progress_metadata,
    Column("request_id", Text, primary_key=True),
    Column("steps_total", Integer, nullable=False),
    Column("steps_done", Integer, nullable=False),
    Column("current_step", Text, nullable=True),
    Column("estimated_completion", DateTime(timezone=True), nullable=True),
    Column("partial_findings_available", Boolean, nullable=False),
)


def to_progress_response(row: Mapping[str, Any]) -> dict[str, Any]:
    """Map one ``progress`` row onto the §41.1 progress projection."""
    data = dict(row)
    return {
        "steps_total": int(data.get("steps_total") or 0),
        "steps_done": int(data.get("steps_done") or 0),
        "current_step": data.get("current_step") or "RECEIVING",
        "estimated_completion": as_iso(data.get("estimated_completion")),
        "partial_findings_available": bool(data.get("partial_findings_available")),
    }


class ProgressRepository(TableRepository):
    """§41.1 — the progress of one request, one row per request."""

    _metadata = progress_metadata
    _table = progress_table

    @classmethod
    async def save(
        cls,
        engine: Any,
        request_id: str,
        *,
        steps_total: int,
        steps_done: int,
        current_step: str | None,
        partial_findings_available: bool,
        estimated_completion: datetime | None = None,
    ) -> dict[str, Any]:
        """Write the progress of *request_id*, replacing the previous snapshot.

        ``steps_done`` is clamped to ``steps_total``: a progress that claims more
        steps done than the plan has would be a state the run cannot reach.
        """
        await cls.ensure_table(engine)
        total = max(0, int(steps_total))
        done = min(max(0, int(steps_done)), total) if total else max(0, int(steps_done))
        row = {
            "request_id": request_id,
            "steps_total": total,
            "steps_done": done,
            "current_step": current_step,
            "estimated_completion": estimated_completion,
            # §41.1 — des résultats partiels ne sont annoncés que s'il y en a :
            # « true » sans contenu serait une promesse creuse.
            "partial_findings_available": bool(partial_findings_available),
        }
        statement = insert_statement(progress_table, engine).values(**row)
        statement = statement.on_conflict_do_update(
            index_elements=["request_id"],
            set_={
                "steps_total": row["steps_total"],
                "steps_done": row["steps_done"],
                "current_step": row["current_step"],
                "estimated_completion": row["estimated_completion"],
                "partial_findings_available": row["partial_findings_available"],
            },
        )
        async with engine.begin() as conn:
            await conn.execute(statement)
        return to_progress_response(row)

    @classmethod
    async def get(cls, engine: Any, request_id: str) -> dict[str, Any] | None:
        """Return the last persisted progress of *request_id*, or ``None``."""
        await cls.ensure_table(engine)
        async with engine.connect() as conn:
            result = await conn.execute(
                select(progress_table).where(progress_table.c.request_id == request_id)
            )
            row = result.mappings().first()
        return to_progress_response(row) if row else None

    @classmethod
    async def clear(cls, engine: Any, request_id: str) -> bool:
        """Remove the progress row of one request (administrative reset)."""
        await cls.ensure_table(engine)
        from sqlalchemy import delete

        async with engine.begin() as conn:
            result = await conn.execute(
                delete(progress_table).where(progress_table.c.request_id == request_id)
            )
        return bool(result.rowcount)