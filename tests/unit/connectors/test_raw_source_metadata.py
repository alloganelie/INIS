"""§9.1/§11 — le matériau relu porte son type réel et sa localisation.

Une unité §11 n'est traçable que si la source nomme le fichier dont elle vient et
le type réellement lu. ``retrieve()`` se contentait de recopier les métadonnées du
candidat (``{"filename": …}``) : ni ``content_type``, ni ``location`` — donc rien
qui permette de revenir au fichier.

Ce fichier verrouille les deux garanties ajoutées en L2.4 : le ``content_type`` de
la lecture (celui du connecteur, ou celui que le stockage objet déclare) et la
``location`` réellement ouverte, pour les six connecteurs §9.1 et pour les deux
modes (glob et cible explicite ``s3://``).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from app.connectors.base import Query, SourceCandidate
from app.connectors.files import explicit_target as explicit_module
from app.connectors.files.csv_connector import CSVConnector
from app.connectors.files.docx_connector import CONTENT_TYPE as DOCX_CONTENT_TYPE
from app.connectors.files.docx_connector import DOCXConnector
from app.connectors.files.excel_connector import CONTENT_TYPE as XLSX_CONTENT_TYPE
from app.connectors.files.excel_connector import ExcelConnector
from app.connectors.files.json_connector import JSONConnector
from app.connectors.files.pdf_connector import CONTENT_TYPE as PDF_CONTENT_TYPE
from app.connectors.files.pdf_connector import PDFConnector
from app.connectors.files.xml_connector import XMLConnector
from app.core.errors import ValidationError
from app.storage.object_storage.object_downloader import DownloadedObject

CSV_CONTENT_TYPE = "text/csv"
JSON_CONTENT_TYPE = "application/json"
XML_CONTENT_TYPE = "application/xml"

#: (connector factory, file name, content type) — one per §9.1 file connector.
CONNECTORS = [
    (CSVConnector, "villes.csv", CSV_CONTENT_TYPE),
    (JSONConnector, "villes.json", JSON_CONTENT_TYPE),
    (XMLConnector, "villes.xml", XML_CONTENT_TYPE),
    (ExcelConnector, "villes.xlsx", XLSX_CONTENT_TYPE),
    (PDFConnector, "villes.pdf", PDF_CONTENT_TYPE),
    (DOCXConnector, "villes.docx", DOCX_CONTENT_TYPE),
]
#: (connector factory, file name) — the cases that do not need the content type.
FILES = [(factory, name) for factory, name, _ in CONNECTORS]
IDS = ["csv", "json", "xml", "excel", "pdf", "docx"]


@pytest.mark.parametrize(("factory", "name", "content_type"), CONNECTORS, ids=IDS)
async def test_an_explicit_target_keeps_its_content_type_and_location(
    factory: type, name: str, content_type: str, tmp_path: Path
) -> None:
    """§11 — type réel et localisation réelle, pour le mode cible explicite."""
    target = tmp_path / name
    target.write_bytes(b"contenu")
    connector = factory(str(tmp_path))

    candidate = (await connector.discover(Query(filters={"location": str(target)})))[0]
    raw = await connector.retrieve(candidate)

    assert raw.content_type == content_type
    assert raw.metadata["content_type"] == content_type
    assert raw.metadata["location"] == str(target)
    assert raw.metadata["resolved_location"] == str(target.resolve())
    assert raw.metadata["size_bytes"] == str(len(b"contenu"))
    assert raw.metadata["origin"] == "explicit_target"


@pytest.mark.parametrize(("factory", "name", "content_type"), CONNECTORS, ids=IDS)
async def test_a_globbed_candidate_also_carries_them(
    factory: type, name: str, content_type: str, tmp_path: Path
) -> None:
    """Le mode glob n'est pas oublié : il localise aussi ce qu'il a trouvé."""
    target = tmp_path / name
    target.write_bytes(b"contenu")
    connector = factory(str(tmp_path))

    candidate = (await connector.discover(Query(query_string="villes")))[0]
    raw = await connector.retrieve(candidate)

    assert raw.content_type == content_type
    assert raw.metadata["location"] == str(target)
    assert raw.metadata["filename"] == name


@pytest.mark.parametrize(("factory", "name"), FILES, ids=IDS)
async def test_an_object_sourced_candidate_is_read_and_located(
    factory: type, name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§9.1 — une cible ``s3://`` est streamée puis relue, et reste localisable."""
    downloaded = tmp_path / "telecharge"
    downloaded.write_bytes(b"contenu distant")
    uri = f"s3://inis-artifacts/documents/REQ_1/{name}"
    calls: list[str] = []

    @contextmanager
    def _fake_download(target: str, **kwargs: Any) -> Iterator[DownloadedObject]:
        calls.append(target)
        yield DownloadedObject(
            uri=target,
            path=downloaded,
            bucket="inis-artifacts",
            key=f"documents/REQ_1/{name}",
            size_bytes=len(b"contenu distant"),
            content_type="application/x-custom",
        )

    monkeypatch.setattr(explicit_module, "download_object_to_temp", _fake_download)
    connector = factory(str(tmp_path))

    candidate = (await connector.discover(Query(filters={"location": uri})))[0]
    raw = await connector.retrieve(candidate)

    assert calls == [uri]
    assert raw.metadata["location"] == uri
    assert raw.metadata["storage_ref"] == uri
    assert raw.metadata["origin"] == "object_storage"
    assert raw.metadata["size_bytes"] == str(len(b"contenu distant"))
    # §9.1 — le type déclaré par le stockage est le type réel : il gagne.
    assert raw.content_type == "application/x-custom"
    assert raw.metadata["content_type"] == "application/x-custom"


@pytest.mark.parametrize(("factory", "name"), FILES, ids=IDS)
async def test_the_connector_type_is_kept_when_the_backend_declares_none(
    factory: type, name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sans type côté stockage, le connecteur garde le sien — jamais ``None``."""
    downloaded = tmp_path / "telecharge-sans-type"
    downloaded.write_bytes(b"contenu distant")
    uri = f"s3://inis-artifacts/documents/REQ_1/{name}"

    @contextmanager
    def _fake_download(target: str, **kwargs: Any) -> Iterator[DownloadedObject]:
        yield DownloadedObject(
            uri=target,
            path=downloaded,
            bucket="inis-artifacts",
            key=f"documents/REQ_1/{name}",
            size_bytes=len(b"contenu distant"),
            content_type=None,
        )

    monkeypatch.setattr(explicit_module, "download_object_to_temp", _fake_download)
    connector = factory(str(tmp_path))
    expected = next(ct for fac, _, ct in CONNECTORS if fac is factory)

    candidate = (await connector.discover(Query(filters={"location": uri})))[0]
    raw = await connector.retrieve(candidate)

    assert raw.content_type == expected
    assert raw.metadata["content_type"] == expected


@pytest.mark.parametrize(("factory", "name"), FILES, ids=IDS)
async def test_a_source_larger_than_the_limit_is_refused(
    factory: type, name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§41.2 — ``[limits].max_upload_bytes`` borne aussi ce que INIS accepte de lire."""
    monkeypatch.setenv("INIS_MAX_UPLOAD_BYTES", "4")
    target = tmp_path / name
    target.write_bytes(b"bien plus que quatre octets")
    connector = factory(str(tmp_path))

    candidate = (await connector.discover(Query(filters={"location": str(target)})))[0]

    with pytest.raises(ValidationError) as refusal:
        await connector.retrieve(candidate)

    assert "limite autorisée de 4 octets" in str(refusal.value)


@pytest.mark.parametrize(("factory", "name"), FILES, ids=IDS)
async def test_a_missing_file_still_raises_file_not_found(
    factory: type, name: str, tmp_path: Path
) -> None:
    """§25.2 — l'erreur sous-jacente est propagée, pas remplacée."""
    connector = factory(str(tmp_path))
    candidate = SourceCandidate(
        source_id=f"{name}-absent",
        location=str(tmp_path / name),
        metadata={"filename": name},
    )

    with pytest.raises(FileNotFoundError):
        await connector.retrieve(candidate)

