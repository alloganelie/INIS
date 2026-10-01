"""Versions, lignage et livraisons d'un artefact (§24.2, §18.1, §24.3).

Les trois tables existaient depuis les révisions ``0005``/``0007`` et étaient
**vides** : un artefact livré n'avait donc qu'une version implicite (la colonne
``artifacts.version``), aucune histoire, et aucun moyen de savoir de quelles
sources, transformations ou informations il provenait.

Trois principes gouvernent ce module :

* **rien n'est réinventé** : les identifiants de provenance sont ceux que la
  livraison porte déjà (``source_ids``, ``dataset_ids``, ``transformation_ids``
  du §24.2) plus les ``information_id`` des unités livrées — la provenance
  existante, pas un second mécanisme ;
* **append-only** : une version publiée ne se réécrit pas. L'insertion est
  idempotente (``ON CONFLICT DO NOTHING``) et **aucune** de ces tables ne reçoit
  de ``deleted_at`` — décision ``0016`` : elles sont l'historique, une
  suppression logique de l'artefact ne doit pas l'effacer ;
* **ids déterministes** : ``AV_<artifact_id>_<version>`` et
  ``AL_<artifact_id>_<version>``. Aucun préfixe ULID inventé (§0.3, table
  fermée), et réenregistrer la même version ne crée pas de doublon.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    Column,
    DateTime,
    MetaData,
    String,
    Table,
    Text,
    select,
)

from app.storage.repositories.artifact_repository import as_list
from app.storage.repositories.table_repository import (
    JSON_TYPE,
    TableRepository,
    as_iso,
    insert_statement,
)

__all__ = [
    "ArtifactDeliveryEventRepository",
    "ArtifactLineageRepository",
    "ArtifactVersionRepository",
    "artifact_delivery_events_table",
    "artifact_lineage_table",
    "artifact_versions_table",
    "bump_version",
    "record_delivered_version",
    "semver_key",
]

#: The §24.2 ``major.minor.patch`` shape, as ``ArtifactVersion`` validates it.
SEMVER_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")

artifact_metadata = MetaData()

artifact_versions_table = Table(
    "artifact_versions",
    artifact_metadata,
    Column("artifact_version_id", Text, primary_key=True),
    Column("artifact_id", Text, nullable=False),
    Column("version", String(32), nullable=False),
    Column("metadata", JSON_TYPE, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

artifact_lineage_table = Table(
    "artifact_lineage",
    artifact_metadata,
    Column("artifact_lineage_id", Text, primary_key=True),
    Column("artifact_id", Text, nullable=False),
    Column("source_ids", JSON_TYPE, nullable=False),
    Column("dataset_ids", JSON_TYPE, nullable=False),
    Column("transformation_ids", JSON_TYPE, nullable=False),
)

artifact_delivery_events_table = Table(
    "artifact_delivery_events",
    artifact_metadata,
    Column("delivery_event_id", Text, primary_key=True),
    Column("artifact_id", String(64), nullable=False),
    Column("target", Text, nullable=False),
    Column("status", String(40), nullable=False),
    Column("delivered_at", DateTime(timezone=True), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)


def semver_key(version: str) -> tuple[int, int, int]:
    """Return the sortable key of a semver string (§24.2).

    Comparing versions as text would rank ``1.10.0`` below ``1.9.0``; the key is
    therefore numeric. A malformed version sorts last instead of raising: the
    history must stay readable even if one row was written by an older build.
    """
    if not SEMVER_PATTERN.match(version or ""):
        return (2**31, 2**31, 2**31)
    major, minor, patch = (int(part) for part in version.split("."))
    return (major, minor, patch)


def bump_version(version: str, kind: str = "patch") -> str:
    """Return the next version of *version*, per the *kind* of change.

    Raises:
        ValueError: for an unknown bump kind or a malformed version — inventing a
            version number would make the history lie.
    """
    if not SEMVER_PATTERN.match(version or ""):
        raise ValueError(f"version '{version}' is not a semantic version (§24.2)")
    major, minor, patch = semver_key(version)
    if kind == "major":
        return f"{major + 1}.0.0"
    if kind == "minor":
        return f"{major}.{minor + 1}.0"
    if kind == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise ValueError(f"unknown version bump '{kind}' (expected major, minor or patch)")


def to_version_response(row: Mapping[str, Any]) -> dict[str, Any]:
    """Map one ``artifact_versions`` row onto its API projection."""
    data = dict(row)
    return {
        "artifact_version_id": data.get("artifact_version_id"),
        "artifact_id": data.get("artifact_id"),
        "version": data.get("version"),
        "metadata": dict(data.get("metadata") or {}),
        "created_at": as_iso(data.get("created_at")),
    }


def to_lineage_response(row: Mapping[str, Any]) -> dict[str, Any]:
    """Map one ``artifact_lineage`` row onto its API projection."""
    data = dict(row)
    return {
        "artifact_lineage_id": data.get("artifact_lineage_id"),
        "artifact_id": data.get("artifact_id"),
        "source_ids": as_list(data.get("source_ids")),
        "dataset_ids": as_list(data.get("dataset_ids")),
        "transformation_ids": as_list(data.get("transformation_ids")),
    }


def to_delivery_event_response(row: Mapping[str, Any]) -> dict[str, Any]:
    """Map one ``artifact_delivery_events`` row onto its API projection."""
    data = dict(row)
    return {
        "delivery_event_id": data.get("delivery_event_id"),
        "artifact_id": data.get("artifact_id"),
        "target": data.get("target"),
        "status": data.get("status"),
        "delivered_at": as_iso(data.get("delivered_at")),
        "created_at": as_iso(data.get("created_at")),
    }


class ArtifactVersionRepository(TableRepository):
    """Append-only history of the versions of an artifact (§18.1)."""

    _metadata = artifact_metadata
    _table = artifact_versions_table

    @staticmethod
    def version_id(artifact_id: str, version: str) -> str:
        """Return the deterministic identifier of one version of an artifact."""
        return f"AV_{artifact_id}_{version}"

    @classmethod
    async def append(
        cls,
        engine: Any,
        artifact_id: str,
        version: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Append one version; re-appending it is a no-op, never a rewrite.

        A published version is immutable: an existing row is left untouched and
        returned as it is, so the history cannot be rewritten by a second run.
        """
        if not SEMVER_PATTERN.match(version or ""):
            raise ValueError(f"version '{version}' is not a semantic version (§24.2)")
        await cls.ensure_table(engine)
        row = {
            "artifact_version_id": cls.version_id(artifact_id, version),
            "artifact_id": artifact_id,
            "version": version,
            "metadata": dict(metadata or {}),
            "created_at": datetime.now(UTC),
        }
        statement = insert_statement(artifact_versions_table, engine).values(**row)
        statement = statement.on_conflict_do_nothing(index_elements=["artifact_version_id"])
        async with engine.begin() as conn:
            await conn.execute(statement)
        stored = await cls.get(engine, row["artifact_version_id"])
        return stored or to_version_response(row)

    @classmethod
    async def get(cls, engine: Any, artifact_version_id: str) -> dict[str, Any] | None:
        """Return one version row by identifier."""
        await cls.ensure_table(engine)
        async with engine.connect() as conn:
            result = await conn.execute(
                select(artifact_versions_table).where(
                    artifact_versions_table.c.artifact_version_id == artifact_version_id
                )
            )
            row = result.mappings().first()
        return to_version_response(row) if row else None

    @classmethod
    async def list_for_artifact(cls, engine: Any, artifact_id: str) -> list[dict[str, Any]]:
        """Return every version of an artifact, oldest first."""
        await cls.ensure_table(engine)
        async with engine.connect() as conn:
            result = await conn.execute(
                select(artifact_versions_table).where(
                    artifact_versions_table.c.artifact_id == artifact_id
                )
            )
            rows = [to_version_response(row) for row in result.mappings().all()]
        return sorted(rows, key=lambda item: semver_key(str(item["version"])))

    @classmethod
    async def current(cls, engine: Any, artifact_id: str) -> dict[str, Any] | None:
        """Return the highest version of an artifact, or ``None``."""
        history = await cls.list_for_artifact(engine, artifact_id)
        return history[-1] if history else None


class ArtifactLineageRepository(TableRepository):
    """The inputs an artifact was derived from, appended per version (§24.2)."""

    _metadata = artifact_metadata
    _table = artifact_lineage_table

    @staticmethod
    def lineage_id(artifact_id: str, version: str) -> str:
        """Return the deterministic identifier of one artifact version's lineage."""
        return f"AL_{artifact_id}_{version}"

    @classmethod
    async def append(
        cls,
        engine: Any,
        artifact_id: str,
        version: str,
        *,
        source_ids: Sequence[str] = (),
        dataset_ids: Sequence[str] = (),
        transformation_ids: Sequence[str] = (),
    ) -> dict[str, Any]:
        """Append the lineage of one version; never rewrite an existing row."""
        await cls.ensure_table(engine)
        row = {
            "artifact_lineage_id": cls.lineage_id(artifact_id, version),
            "artifact_id": artifact_id,
            "source_ids": list(dict.fromkeys(str(item) for item in source_ids)),
            "dataset_ids": list(dict.fromkeys(str(item) for item in dataset_ids)),
            "transformation_ids": list(
                dict.fromkeys(str(item) for item in transformation_ids)
            ),
        }
        statement = insert_statement(artifact_lineage_table, engine).values(**row)
        statement = statement.on_conflict_do_nothing(index_elements=["artifact_lineage_id"])
        async with engine.begin() as conn:
            await conn.execute(statement)
        async with engine.connect() as conn:
            result = await conn.execute(
                select(artifact_lineage_table).where(
                    artifact_lineage_table.c.artifact_lineage_id == row["artifact_lineage_id"]
                )
            )
            stored = result.mappings().first()
        return to_lineage_response(stored or row)

    @classmethod
    async def list_for_artifact(cls, engine: Any, artifact_id: str) -> list[dict[str, Any]]:
        """Return the lineage of every version of an artifact."""
        await cls.ensure_table(engine)
        async with engine.connect() as conn:
            result = await conn.execute(
                select(artifact_lineage_table).where(
                    artifact_lineage_table.c.artifact_id == artifact_id
                )
            )
            rows = [to_lineage_response(row) for row in result.mappings().all()]
        return sorted(rows, key=lambda item: semver_key(_version_of(str(item["artifact_lineage_id"]))))

    @classmethod
    async def get_for_version(
        cls, engine: Any, artifact_id: str, version: str
    ) -> dict[str, Any] | None:
        """Return the lineage recorded for one version, or ``None``."""
        await cls.ensure_table(engine)
        async with engine.connect() as conn:
            result = await conn.execute(
                select(artifact_lineage_table).where(
                    artifact_lineage_table.c.artifact_lineage_id
                    == cls.lineage_id(artifact_id, version)
                )
            )
            row = result.mappings().first()
        return to_lineage_response(row) if row else None


def _version_of(lineage_id: str) -> str:
    """Return the version encoded in an ``AL_<artifact_id>_<version>`` id."""
    parts = lineage_id.split("_")
    return "_".join(parts[-3:]) if len(parts) >= 3 else ""


class ArtifactDeliveryEventRepository(TableRepository):
    """One row per delivery of an artifact's bytes (§24.3)."""

    _metadata = artifact_metadata
    _table = artifact_delivery_events_table

    @classmethod
    async def record(
        cls,
        engine: Any,
        artifact_id: str,
        *,
        target: str,
        status: str = "delivered",
        delivered_at: datetime | None = None,
    ) -> dict[str, Any]:
        """Append one delivery event; the identifier is derived from its content.

        The identifier is a digest of ``(artifact_id, target, timestamp)``: two
        downloads are two events, a replay of the same instant is not. No ULID
        prefix is invented (§0.3, closed table).
        """
        await cls.ensure_table(engine)
        created_at = datetime.now(UTC)
        moment = delivered_at or created_at
        digest = hashlib.sha256(
            f"{artifact_id}|{target}|{moment.isoformat()}".encode()
        ).hexdigest()[:32]
        row = {
            "delivery_event_id": f"DEV_{digest}",
            "artifact_id": artifact_id,
            "target": target,
            "status": status,
            "delivered_at": moment,
            "created_at": created_at,
        }
        statement = insert_statement(artifact_delivery_events_table, engine).values(**row)
        statement = statement.on_conflict_do_nothing(index_elements=["delivery_event_id"])
        async with engine.begin() as conn:
            await conn.execute(statement)
        return to_delivery_event_response(row)

    @classmethod
    async def list_for_artifact(cls, engine: Any, artifact_id: str) -> list[dict[str, Any]]:
        """Return the delivery events of an artifact, oldest first."""
        await cls.ensure_table(engine)
        async with engine.connect() as conn:
            result = await conn.execute(
                select(artifact_delivery_events_table)
                .where(artifact_delivery_events_table.c.artifact_id == artifact_id)
                .order_by(artifact_delivery_events_table.c.created_at)
            )
            return [to_delivery_event_response(row) for row in result.mappings().all()]


async def record_delivered_version(
    engine: Any,
    record: Mapping[str, Any],
    *,
    information_ids: Sequence[str] = (),
) -> dict[str, Any]:
    """Record the version and the lineage of a **delivered** artifact (§24.2).

    The inputs are those the §24.2 record already carries — the existing
    provenance — plus the ``information_id`` of the delivered units, which is
    what makes ``source → transformation → information → artifact`` readable.

    Returns:
        ``{"version": <row>, "lineage": <row>}``, both append-only.
    """
    artifact_id = str(record.get("artifact_id") or "")
    version = str(record.get("version") or "1.0.0")
    source_ids = [str(item) for item in as_list(record.get("source_ids"))]
    dataset_ids = [str(item) for item in as_list(record.get("dataset_ids"))]
    transformation_ids = [str(item) for item in as_list(record.get("transformation_ids"))]
    metadata = {
        "request_id": record.get("request_id"),
        "file_name": record.get("file_name"),
        "mime_type": record.get("mime_type"),
        "size_bytes": record.get("size_bytes"),
        "sha256": record.get("sha256"),
        "storage_ref": record.get("storage_ref"),
        "source_ids": source_ids,
        "dataset_ids": dataset_ids,
        "transformation_ids": transformation_ids,
        "information_ids": [str(item) for item in dict.fromkeys(information_ids)],
        "delivered_at": record.get("created_at"),
    }
    version_row = await ArtifactVersionRepository.append(engine, artifact_id, version, metadata)
    lineage_row = await ArtifactLineageRepository.append(
        engine,
        artifact_id,
        version,
        source_ids=source_ids,
        dataset_ids=dataset_ids,
        transformation_ids=transformation_ids,
    )
    return {"version": version_row, "lineage": lineage_row}


async def publish_new_version(
    engine: Any,
    artifact: Mapping[str, Any],
    *,
    kind: str = "patch",
    information_ids: Sequence[str] = (),
    transformation_ids: Sequence[str] = (),
    source_ids: Sequence[str] = (),
    dataset_ids: Sequence[str] = (),
    extra_metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Publish the next version of an existing artifact (§18.1).

    The new version is derived from the **current** one, names it as its
    predecessor (``supersedes``) and gets its own lineage row: the history grows,
    it is never rewritten. The ``artifacts.version`` column is advanced so that
    "which version is currently delivered" is readable from the artifact itself
    and stays coherent with :meth:`ArtifactVersionRepository.current`.

    Raises:
        ValueError: when the artifact identifier or its inputs are missing.
    """
    from sqlalchemy import update

    from app.storage.repositories.artifact_repository import artifacts_table

    artifact_id = str(artifact.get("artifact_id") or "")
    if not artifact_id:
        raise ValueError("an artifact identifier is required to publish a version")
    current = await ArtifactVersionRepository.current(engine, artifact_id)
    current_version = str(current["version"]) if current else str(artifact.get("version") or "1.0.0")
    next_version = bump_version(current_version, kind)

    metadata = {
        **dict(current.get("metadata") if current else {}),
        "supersedes": (
            current["artifact_version_id"] if current else None
        ),
        "source_ids": [str(item) for item in dict.fromkeys(source_ids)] or None,
        "dataset_ids": [str(item) for item in dict.fromkeys(dataset_ids)] or None,
        "transformation_ids": [str(item) for item in dict.fromkeys(transformation_ids)] or None,
        "information_ids": [str(item) for item in dict.fromkeys(information_ids)],
        **dict(extra_metadata or {}),
    }
    metadata = {key: value for key, value in metadata.items() if value is not None}

    version_row = await ArtifactVersionRepository.append(
        engine, artifact_id, next_version, metadata
    )
    lineage_row = await ArtifactLineageRepository.append(
        engine,
        artifact_id,
        next_version,
        source_ids=source_ids or (current or {}).get("metadata", {}).get("source_ids", []),
        dataset_ids=dataset_ids or (current or {}).get("metadata", {}).get("dataset_ids", []),
        transformation_ids=transformation_ids,
    )
    async with engine.begin() as conn:
        await conn.execute(
            update(artifacts_table)
            .where(artifacts_table.c.artifact_id == artifact_id)
            .values(version=next_version)
        )
    return {"version": version_row, "lineage": lineage_row, "supersedes": current}
