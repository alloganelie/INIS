"""``extract_image_content`` internal tool per §21.

Returns the factual :class:`InformationUnit` values that can be *extracted* from
an image file:

* one unit per literal textual tag embedded in the file (EXIF
  ``ImageDescription``, PNG ``tEXt``…) — the text is copied verbatim, never
  summarised;
* one unit describing the image's own technical properties (format, mode,
  dimensions, frame count, DPI) with ``data_stage="derived"`` and the
  transformation identifier that produced it.

There is no OCR and no captioning in INIS V1: an image carrying no text yields
**no** textual unit, and saying otherwise would be an invention (§1.2, §0.2).
"""

from __future__ import annotations

from pathlib import Path

from app.connectors.images.image_connector import read_image_metadata
from app.core.errors import InfrastructureError, ValidationError
from app.core.time import utc_now
from app.domain.entities.information_unit import InformationUnit
from app.domain.value_objects.ulid import ULID

__all__ = ["extract_image_content"]

#: Provenance method recorded on every unit this tool produces.
METHOD = "image_analyzer"

#: ``InformationUnit.type`` used for content located inside an image.
UNIT_TYPE = "image_region"


def _unit(
    *,
    content: dict,
    source_id: str,
    document_id: str,
    storage_ref: str,
    transformation_id: str,
    location: dict,
) -> InformationUnit:
    """Build one provenance-complete derived unit."""
    now = utc_now()
    return InformationUnit(
        information_id=ULID.new("INF_"),
        type=UNIT_TYPE,
        content=content,
        raw_reference={"storage_ref": storage_ref},
        source_id=source_id,
        document_id=document_id,
        dataset_id=None,
        location=location,
        context={},
        language=None,
        unit=None,
        time={},
        classification={},
        quality={},
        confidence={},
        provenance={
            "method": METHOD,
            "transformation_id": transformation_id,
            "storage_ref": storage_ref,
            "extracted_at": now.isoformat(),
        },
        versions=[],
        data_stage="derived",
        created_at=now,
        updated_at=now,
    )


async def extract_image_content(
    path: str,
    *,
    source_id: str,
    document_id: str | None = None,
    transformation_id: str | None = None,
) -> list[InformationUnit]:
    """Extract the traceable content of the image at *path* (§21).

    Args:
        path: Path of the image file.
        source_id: Identifier of the owning source. Keyword-only because
            provenance is a hard invariant: a factual unit MUST reference the
            source it came from (§0.2), and §21's ``extract_image_content(path)``
            cannot supply it on its own.
        document_id: Identifier of the image document; a ``DOC_`` identifier is
            minted when omitted.
        transformation_id: ``TRF_{ULID}`` identifier of the extraction
            transformation; minted when omitted.

    Returns:
        One derived unit per embedded textual tag, followed by one unit
        describing the technical properties of the image.

    Raises:
        ValidationError: If *path* does not exist or *source_id* is empty.
        InfrastructureError: If Pillow is unavailable or the payload cannot be
            decoded (INIS never reports an unreadable image as empty).
    """
    file_path = Path(path)
    if not file_path.is_file():
        raise ValidationError(f"image file not found: {path}")
    if not source_id or not str(source_id).strip():
        raise ValidationError("source_id is required to extract factual image content (§0.2)")

    storage_ref = file_path.resolve().as_uri()
    try:
        metadata = read_image_metadata(file_path.read_bytes())
    except Exception as exc:
        raise InfrastructureError(f"could not decode image {path}: {exc}") from exc
    if not metadata.pillow_available:
        raise InfrastructureError(
            "Pillow is required to extract image content (optional dependency, D6)"
        )

    document = document_id or ULID.new("DOC_")
    transformation = transformation_id or ULID.new("TRF_")
    units: list[InformationUnit] = []

    for tag, value in sorted(metadata.textual_tags.items()):
        units.append(
            _unit(
                content={"text": value},
                source_id=source_id,
                document_id=document,
                storage_ref=storage_ref,
                transformation_id=transformation,
                location={"tag": tag, "kind": "embedded_text"},
            )
        )

    units.append(
        _unit(
            content={
                "format": metadata.format,
                "mode": metadata.mode,
                "width": metadata.width,
                "height": metadata.height,
                "frames": metadata.frames,
                "dpi": list(metadata.dpi) if metadata.dpi else None,
                "has_transparency": metadata.has_transparency,
            },
            source_id=source_id,
            document_id=document,
            storage_ref=storage_ref,
            transformation_id=transformation,
            location={"kind": "image_properties"},
        )
    )
    return units
