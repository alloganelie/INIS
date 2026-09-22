"""XML connector for INIS per §9.1."""

from pathlib import Path

from app.connectors.base import (
    ConnectorMetadata,
    HealthStatus,
    Query,
    RawSource,
    SourceCandidate,
    SourceConnector,
    SourceMetadata,
)


def _strip_namespace(tag: str) -> str:
    """Return the local tag name without any ``{uri}`` prefix."""
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _parse_root(data: bytes) -> tuple[str, list[str], dict[str, str]]:
    """Parse XML with lxml (primary) or stdlib ElementTree (fallback).

    Returns:
        Tuple of (root local tag, child local tags, namespaces).
    """
    try:
        from lxml import etree

        root = etree.fromstring(data)
        children = [_strip_namespace(child.tag) for child in root]
        namespaces = {k or "": v for k, v in root.nsmap.items()}
        return _strip_namespace(root.tag), children, namespaces
    except ImportError:
        import xml.etree.ElementTree as ET

        root = ET.fromstring(data)
        children = [_strip_namespace(child.tag) for child in root]
        return _strip_namespace(root.tag), children, {}


def _collect_namespaces(data: bytes) -> dict[str, str]:
    """Collect namespace declarations (stdlib path, ``start-ns`` events)."""
    import io
    import xml.etree.ElementTree as ET

    namespaces: dict[str, str] = {}
    try:
        for _, (prefix, uri) in ET.iterparse(io.BytesIO(data), events=("start-ns",)):
            namespaces[prefix or ""] = uri
    except ET.ParseError:
        pass
    return namespaces


class XMLConnector:
    """XML file connector (lxml primary, ElementTree fallback)."""

    connector_id: str = "xml-connector"
    supported_source_types: list[str] = ["xml"]

    def __init__(self, base_path: str = ".") -> None:
        """Initialize the XML connector.

        Args:
            base_path: Base directory for XML file discovery.
        """
        self._base_path = Path(base_path)

    async def discover(self, query: Query) -> list[SourceCandidate]:
        """Discover XML files matching the query.

        Args:
            query: Query for source discovery.

        Returns:
            List of source candidates.
        """
        candidates: list[SourceCandidate] = []
        for xml_file in self._base_path.glob("*.xml"):
            if query.query_string.lower() in xml_file.name.lower():
                candidates.append(
                    SourceCandidate(
                        source_id=f"xml-{xml_file.stem}",
                        location=str(xml_file),
                        metadata={"filename": xml_file.name},
                    )
                )
        return candidates

    async def retrieve(self, candidate: SourceCandidate) -> RawSource:
        """Retrieve raw XML data from a candidate.

        Args:
            candidate: Source candidate to retrieve.

        Returns:
            Raw source data.
        """
        file_path = Path(candidate.location)
        content = file_path.read_text(encoding="utf-8")
        return RawSource(
            source_id=candidate.source_id,
            data=content,
            content_type="application/xml",
            metadata=candidate.metadata,
        )

    async def inspect(self, raw: RawSource) -> SourceMetadata:
        """Inspect raw XML: size, root tag, child tags and namespaces.

        Args:
            raw: Raw source data.

        Returns:
            Source metadata.
        """
        payload = raw.data.encode("utf-8") if isinstance(raw.data, str) else bytes(raw.data)
        size_bytes = len(payload)
        try:
            root_tag, child_tags, namespaces = _parse_root(payload)
            if not namespaces:
                namespaces = _collect_namespaces(payload)
        except Exception:
            return SourceMetadata(
                source_id=raw.source_id,
                size_bytes=size_bytes,
                record_count=0,
            )
        schema = {"root": root_tag}
        if child_tags:
            schema["child_tags"] = ",".join(sorted(set(child_tags)))
        if namespaces:
            schema["namespaces"] = ",".join(sorted(namespaces.values()))
        return SourceMetadata(
            source_id=raw.source_id,
            size_bytes=size_bytes,
            record_count=len(child_tags),
            schema=schema,
        )

    async def health_check(self) -> HealthStatus:
        """Check if the connector is healthy.

        Returns:
            Health status.
        """
        return HealthStatus(healthy=True, message="XML connector healthy")

    async def metadata(self) -> ConnectorMetadata:
        """Get connector metadata.

        Returns:
            Connector metadata.
        """
        return ConnectorMetadata(
            connector_id=self.connector_id,
            name="XML Connector",
            version="1.0.0",
            supported_source_types=self.supported_source_types,
        )
