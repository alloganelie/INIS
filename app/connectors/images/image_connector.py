"""Image connector for INIS per §9.1 and §1.1 ("analyser des images simples").

The connector reads *technical* image metadata with Pillow (format, mode,
dimensions, frame count, DPI, embedded textual tags) and nothing else. It
never guesses a semantic label: INIS V1 must not invent information (§1.2,
§0.2), so any textual ``InformationUnit`` produced downstream comes from
strings literally embedded in the file (EXIF ``ImageDescription``, PNG tEXt
chunks…), never from an OCR or captioning model.

Pillow is an *optional* dependency of the V1 stack (§4.1, decision D6): when
it is missing the connector still discovers and retrieves bytes, but
``inspect`` degrades to size-only metadata and ``health_check`` reports the
degradation explicitly instead of pretending the image was analysed.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.connectors.base import (
    ConnectorMetadata,
    HealthStatus,
    Query,
    RawSource,
    SourceCandidate,
    SourceMetadata,
)

#: File extensions handled by this connector (lower case, without the dot).
IMAGE_EXTENSIONS: tuple[str, ...] = (
    "png",
    "jpg",
    "jpeg",
    "gif",
    "bmp",
    "tif",
    "tiff",
    "webp",
)

#: ``MIME`` type per extension, used when the candidate carries no hint.
MIME_TYPES: dict[str, str] = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "bmp": "image/bmp",
    "tif": "image/tiff",
    "tiff": "image/tiff",
    "webp": "image/webp",
}

#: EXIF/PNG textual keys kept as literal, source-provided strings.
TEXTUAL_TAG_KEYS: tuple[str, ...] = (
    "ImageDescription",
    "Artist",
    "Copyright",
    "Software",
    "UserComment",
    "XPComment",
    "DocumentName",
    "Title",
    "Author",
    "Description",
    "Comment",
)


def _pillow():
    """Return the ``PIL.Image`` module or ``None`` when Pillow is absent (D6)."""
    try:
        from PIL import Image  # noqa: PLC0415 - optional dependency (D6)
    except ImportError:
        return None
    return Image


@dataclass(frozen=True)
class ImageMetadata:
    """Technical description of an image, extracted from its own bytes only."""

    format: str | None = None
    mode: str | None = None
    width: int = 0
    height: int = 0
    frames: int = 1
    dpi: tuple[float, float] | None = None
    textual_tags: dict[str, str] = field(default_factory=dict)
    exif_tag_count: int = 0
    has_transparency: bool = False
    pillow_available: bool = True

    @property
    def pixel_count(self) -> int:
        """Return ``width * height`` (0 when the image could not be opened)."""
        return self.width * self.height

    @property
    def text_source(self) -> str | None:
        """Return the first literal textual tag value, or ``None``.

        A non-``None`` value is a verbatim string stored *in* the file and may
        therefore back a factual ``InformationUnit``; ``None`` means the image
        carries no text, and no unit may be invented for it (§1.2, §0.2).
        """
        for key in TEXTUAL_TAG_KEYS:
            value = self.textual_tags.get(key)
            if value and value.strip():
                return value
        for key in sorted(self.textual_tags):
            value = self.textual_tags[key]
            if value and value.strip():
                return value
        return None

    def to_schema(self) -> dict[str, str]:
        """Project the metadata onto the ``dict[str, str]`` connector schema."""
        schema: dict[str, str] = {
            "format": str(self.format or "unknown"),
            "mode": str(self.mode or "unknown"),
            "width": str(self.width),
            "height": str(self.height),
            "frames": str(self.frames),
            "exif_tags": str(self.exif_tag_count),
            "has_transparency": str(self.has_transparency),
            "pillow_available": str(self.pillow_available),
        }
        if self.dpi is not None:
            schema["dpi_x"] = str(self.dpi[0])
            schema["dpi_y"] = str(self.dpi[1])
        for key in sorted(self.textual_tags):
            schema[f"text:{key}"] = self.textual_tags[key]
        return schema


def _decode_tag_value(value: Any) -> str | None:
    """Decode a Pillow tag value into a plain non-empty string."""
    if value is None:
        return None
    if isinstance(value, bytes):
        for encoding in ("utf-8", "utf-16", "latin-1"):
            try:
                decoded = value.decode(encoding)
            except (UnicodeDecodeError, LookupError):
                continue
            decoded = decoded.replace("\x00", "").strip()
            if decoded:
                return decoded
        return None
    if isinstance(value, (list, tuple)):
        text = " ".join(str(item) for item in value).strip()
        return text or None
    text = str(value).strip()
    return text or None


def read_image_metadata(data: bytes) -> ImageMetadata:
    """Read technical image metadata from *data* with Pillow.

    Args:
        data: Raw image bytes.

    Returns:
        The extracted :class:`ImageMetadata`. When Pillow is unavailable the
        result carries ``pillow_available=False`` and zeroed dimensions, which
        makes the degradation visible instead of silent (§0.2, D6).
    """
    Image = _pillow()
    if Image is None:
        return ImageMetadata(pillow_available=False)

    with Image.open(io.BytesIO(data)) as image:
        dpi_value = image.info.get("dpi")
        dpi: tuple[float, float] | None = None
        if isinstance(dpi_value, (tuple, list)) and len(dpi_value) == 2:
            try:
                dpi = (float(dpi_value[0]), float(dpi_value[1]))
            except (TypeError, ValueError):
                dpi = None

        textual: dict[str, str] = {}
        # PNG / WebP literal text chunks live in ``image.info``.
        for key, raw_value in image.info.items():
            if key in TEXTUAL_TAG_KEYS:
                decoded = _decode_tag_value(raw_value)
                if decoded:
                    textual[key] = decoded

        exif_tag_count = 0
        try:
            exif = image.getexif()
        except Exception:
            exif = None
        if exif:
            try:
                from PIL.ExifTags import TAGS  # noqa: PLC0415 - optional (D6)

                exif_tag_count = len(exif)
                for tag_id, raw_value in exif.items():
                    name = TAGS.get(tag_id, str(tag_id))
                    if name not in TEXTUAL_TAG_KEYS:
                        continue
                    decoded = _decode_tag_value(raw_value)
                    if decoded:
                        textual.setdefault(name, decoded)
            except Exception:
                exif_tag_count = 0

        return ImageMetadata(
            format=getattr(image, "format", None),
            mode=getattr(image, "mode", None),
            width=int(image.size[0]),
            height=int(image.size[1]),
            frames=int(getattr(image, "n_frames", 1) or 1),
            dpi=dpi,
            textual_tags=textual,
            exif_tag_count=exif_tag_count,
            has_transparency=(
                getattr(image, "mode", "") in {"RGBA", "LA", "PA"}
                or "transparency" in image.info
            ),
        )


class ImageConnector:
    """Discover, retrieve and inspect image files per §9.1 and §1.1."""

    connector_id: str = "image-connector"
    supported_source_types: list[str] = list(IMAGE_EXTENSIONS)

    def __init__(
        self,
        base_path: str = ".",
        extensions: tuple[str, ...] = IMAGE_EXTENSIONS,
    ) -> None:
        """Initialize the image connector.

        Args:
            base_path: Directory scanned by :meth:`discover`.
            extensions: Extensions considered as images.
        """
        self._base_path = Path(base_path)
        self._extensions = tuple(ext.lower().lstrip(".") for ext in extensions)

    async def discover(self, query: Query) -> list[SourceCandidate]:
        """Discover image files whose name matches *query* (§9.1)."""
        candidates: list[SourceCandidate] = []
        for extension in self._extensions:
            for path in sorted(self._base_path.glob(f"*.{extension}")):
                if query.query_string.lower() not in path.name.lower():
                    continue
                candidates.append(
                    SourceCandidate(
                        source_id=f"image-{path.stem}",
                        location=str(path),
                        metadata={
                            "filename": path.name,
                            "extension": extension,
                            "media_type": MIME_TYPES.get(
                                extension, "application/octet-stream"
                            ),
                        },
                    )
                )
        return candidates

    async def retrieve(self, candidate: SourceCandidate) -> RawSource:
        """Return the raw bytes of *candidate* (§9.1)."""
        path = Path(candidate.location)
        payload = path.read_bytes()
        extension = candidate.metadata.get("extension") or path.suffix.lower().lstrip(".")
        return RawSource(
            source_id=candidate.source_id,
            data=payload,
            content_type=MIME_TYPES.get(extension, "application/octet-stream"),
            metadata=dict(candidate.metadata),
        )

    async def inspect(self, raw: RawSource) -> SourceMetadata:
        """Return technical image metadata; size-only when Pillow is absent (§4.1).

        An undecodable payload is *not* silently swallowed: the returned schema
        carries ``decode_error`` so the degraded state is visible to the caller
        and can never be mistaken for a successfully analysed image (§0.2).
        """
        payload = raw.data if isinstance(raw.data, bytes) else raw.data.encode("utf-8")
        try:
            metadata = read_image_metadata(bytes(payload))
        except Exception as exc:
            return SourceMetadata(
                source_id=raw.source_id,
                size_bytes=len(payload),
                record_count=0,
                schema={"format": "unknown", "decode_error": type(exc).__name__},
            )
        return SourceMetadata(
            source_id=raw.source_id,
            size_bytes=len(payload),
            record_count=metadata.frames,
            schema=metadata.to_schema(),
        )

    async def health_check(self) -> HealthStatus:
        """Report whether the Pillow backend is available (§4.1, D6)."""
        if _pillow() is None:
            return HealthStatus(
                healthy=False,
                message="Image connector degraded: Pillow is not installed (D6)",
            )
        return HealthStatus(healthy=True, message="Image connector healthy (Pillow)")

    async def metadata(self) -> ConnectorMetadata:
        """Return the static connector metadata (§9.1)."""
        return ConnectorMetadata(
            connector_id=self.connector_id,
            name="Image Connector",
            version="2.0.0",
            supported_source_types=list(self._extensions),
        )
