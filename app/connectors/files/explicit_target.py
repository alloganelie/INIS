"""§9.1/C3 — a file connector can be pointed at one exact file.

Every file connector discovered its sources with a single ``glob("*.csv")`` of its
base directory. A document stored as an S3 object, a file uploaded to another
path, or an absolute path given by the requester was therefore **invisible**: the
connector answered "no candidate", the request ended with an empty acquisition,
and nothing could tell "the file is not there" from "the connector cannot look
there" (C3).

This module adds the mode the connectors were missing: an explicit target.
``Query.filters["location"]`` names the exact file — a path or an
``s3://bucket/key`` reference — and ``discover`` returns that one candidate
without a glob. The glob behaviour stays the default when no location is given, so
existing callers keep working unchanged.

It also owns the two guarantees §11 needs on the retrieved material: the
``content_type`` really used, and the ``location`` the bytes were read from — a
unit located in a file nobody can name again is not traceable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from app.connectors.base import Query, RawSource, SourceCandidate
from app.core.errors import ValidationError
from app.core.size_limits import effective_max_upload_bytes, size_overflow_message
from app.storage.object_storage.object_downloader import download_object_to_temp

__all__ = [
    "ORIGIN_EXPLICIT",
    "ORIGIN_FILTER",
    "ORIGIN_GLOB",
    "ORIGIN_REMOTE",
    "TARGET_FILTER",
    "DownloadedTarget",
    "TargetSpec",
    "explicit_candidate",
    "explicit_target",
    "is_remote",
    "read_candidate",
]

#: ``Query.filters`` key naming the exact file a connector must read (§9.1).
TARGET_FILTER = "location"

#: Where the read material came from, kept in the §11 metadata.
ORIGIN_FILTER = "origin"
ORIGIN_EXPLICIT = "explicit_target"
ORIGIN_GLOB = "base_path"
ORIGIN_REMOTE = "object_storage"


@dataclass(frozen=True)
class TargetSpec:
    """What one connector accepts as a target, and how it reads it."""

    kind: str
    suffixes: tuple[str, ...]
    content_type: str
    #: ``True`` for formats read as bytes (xlsx, pdf, docx), ``False`` for text.
    binary: bool = False

    @property
    def accepted(self) -> str:
        """Return the accepted suffixes as a human-readable list."""
        return ", ".join(self.suffixes)


@dataclass(frozen=True)
class DownloadedTarget:
    """The material of one read, and the metadata that describes it."""

    data: bytes | str
    metadata: dict[str, str] = field(default_factory=dict)


def explicit_target(query: Query | None) -> str | None:
    """Return the exact target declared by *query*, or ``None`` (glob mode)."""
    filters = getattr(query, "filters", None)
    if not isinstance(filters, dict):
        return None
    raw = filters.get(TARGET_FILTER)
    target = str(raw).strip() if raw is not None else ""
    return target or None


def is_remote(location: str) -> bool:
    """Return whether *location* names an object of the §4.3 object storage."""
    return str(location or "").startswith("s3://")


def _file_name(location: str) -> str:
    """Return the last path segment of *location*, without touching the disk."""
    text = str(location or "").rstrip("/")
    if is_remote(text):
        return PurePosixPath(text).name
    return Path(text).name or text


def _source_id(kind: str, name: str) -> str:
    """Return the candidate identifier of one explicit target."""
    stem = PurePosixPath(name).stem or name
    safe = "".join(char if char.isalnum() or char in "-_" else "-" for char in stem)
    return f"{kind}-{safe or 'target'}"
def explicit_candidate(location: str, spec: TargetSpec) -> SourceCandidate:
    """Return the single candidate of the exact *location* (§9.1).

    Args:
        location: The declared target (path or ``s3://`` reference).
        spec: What this connector reads.

    Returns:
        A candidate whose ``location`` is the declared target itself, so a remote
        object is never globbed nor checked against the local filesystem.

    Raises:
        ValidationError: When the target carries no suffix this connector reads.
            An explicit target is never silently "not found": the caller asked for
            one file, so a file of another type is a refusal that says so.
    """
    target = str(location or "").strip()
    if not target:
        raise ValidationError("Cible explicite vide : aucune source à lire (§9.1).")

    name = _file_name(target)
    suffix = PurePosixPath(name).suffix.lower()
    if suffix not in spec.suffixes:
        raise ValidationError(
            f"Cible '{target}' refusée : le connecteur {spec.kind} ne lit que "
            f"{spec.accepted} (§9.1)."
        )

    return SourceCandidate(
        source_id=_source_id(spec.kind, name),
        location=target,
        metadata={
            "filename": name,
            "location": target,
            "content_type": spec.content_type,
            ORIGIN_FILTER: ORIGIN_EXPLICIT,
        },
    )


def _base_metadata(candidate: SourceCandidate, spec: TargetSpec) -> dict[str, str]:
    """Return the metadata of one read: the location, always, and its origin."""
    location = str(candidate.location or "")
    metadata = {key: str(value) for key, value in dict(candidate.metadata or {}).items()}
    metadata.setdefault("filename", _file_name(location))
    metadata["location"] = location
    metadata.setdefault("content_type", spec.content_type)
    metadata.setdefault(ORIGIN_FILTER, ORIGIN_REMOTE if is_remote(location) else ORIGIN_GLOB)
    return metadata

def _read_local(
    path: Path, candidate: SourceCandidate, spec: TargetSpec
) -> DownloadedTarget:
    """Read one local file, refusing an oversized one before loading it.

    Raises:
        FileNotFoundError: When the path does not exist. The underlying error is
            propagated as such: replacing it would hide which file is missing.
        ValidationError: When the file exceeds ``[limits].max_upload_bytes``.
    """
    size = path.stat().st_size
    limit = effective_max_upload_bytes()
    if size > limit:
        raise ValidationError(size_overflow_message(limit, size, action="Source refusée"))
    metadata = _base_metadata(candidate, spec)
    metadata.update({"size_bytes": str(size), "resolved_location": str(path.resolve())})
    data = path.read_bytes() if spec.binary else path.read_text(encoding="utf-8")
    return DownloadedTarget(data=data, metadata=metadata)


def _read_remote(
    uri: str, candidate: SourceCandidate, spec: TargetSpec
) -> DownloadedTarget:
    """Stream one ``s3://`` object to a temporary file, then read it.

    The object is never loaded as one blob: ``download_object_to_temp`` checks the
    declared size, streams chunk by chunk under the ``[limits]`` ceiling, and
    deletes the temporary file on the way out (§41.13).
    """
    metadata = _base_metadata(candidate, spec)
    with download_object_to_temp(uri) as downloaded:
        data = (
            downloaded.path.read_bytes()
            if spec.binary
            else downloaded.path.read_text(encoding="utf-8")
        )
        metadata.update(
            {
                "location": downloaded.uri,
                "storage_ref": downloaded.uri,
                "size_bytes": str(downloaded.size_bytes),
                ORIGIN_FILTER: ORIGIN_REMOTE,
            }
        )
        if downloaded.content_type:
            # §9.1 — the type the backend declares wins: it is the real one.
            metadata["content_type"] = str(downloaded.content_type)
    return DownloadedTarget(data=data, metadata=metadata)


def read_candidate(candidate: SourceCandidate, spec: TargetSpec) -> RawSource:
    """Return the raw material of *candidate*, with its real §11 metadata.

    Args:
        candidate: A candidate produced by ``discover`` (glob or explicit target).
        spec: What this connector reads.

    Returns:
        The :class:`RawSource` whose ``metadata`` carries the ``content_type`` and
        the ``location`` the bytes were read from.

    Raises:
        ValidationError: When the source is larger than ``[limits].max_upload_bytes``.
        FileNotFoundError: When a local file does not exist.
        InfrastructureError: When the object storage is not configured for an
            ``s3://`` target.
    """
    location = str(candidate.location or "")
    if is_remote(location):
        target = _read_remote(location, candidate, spec)
    else:
        target = _read_local(Path(location), candidate, spec)
    content_type = str(target.metadata.get("content_type") or spec.content_type)
    return RawSource(
        source_id=candidate.source_id,
        data=target.data,
        content_type=content_type,
        metadata=target.metadata,
    )

