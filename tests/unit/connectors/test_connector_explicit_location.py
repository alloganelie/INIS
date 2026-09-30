"""§9.1/C3 — un connecteur fichiers peut être pointé sur un fichier exact.

Le défaut que ce fichier verrouille : ``discover`` ne savait que ``glob("*.csv")``
dans son répertoire de base. Un document stocké en S3, un fichier téléversé
ailleurs, ou un chemin absolu donné par le demandeur étaient donc **invisibles** —
et « le fichier n'est pas là » était indiscernable de « le connecteur ne sait pas
regarder là » (C3).

Le mode « cible explicite » (``Query.filters["location"]``) répond aux deux :
exactement ce fichier, sans glob, et un refus explicite quand le type ne
correspond pas. Le mode glob reste le défaut (non-régression :
``test_csv_connector.py`` passe sans modification).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.connectors.base import Query
from app.connectors.files.csv_connector import CSVConnector
from app.connectors.files.docx_connector import DOCXConnector
from app.connectors.files.excel_connector import ExcelConnector
from app.connectors.files.json_connector import JSONConnector
from app.connectors.files.pdf_connector import PDFConnector
from app.connectors.files.xml_connector import XMLConnector
from app.core.errors import ValidationError

#: (connector factory, file name) — one per §9.1 file connector.
CONNECTORS = [
    (CSVConnector, "villes.csv"),
    (JSONConnector, "villes.json"),
    (XMLConnector, "villes.xml"),
    (ExcelConnector, "villes.xlsx"),
    (PDFConnector, "villes.pdf"),
    (DOCXConnector, "villes.docx"),
]
IDS = ["csv", "json", "xml", "excel", "pdf", "docx"]


@pytest.mark.parametrize(("factory", "name"), CONNECTORS, ids=IDS)
async def test_an_explicit_target_is_returned_without_a_glob(
    factory: type, name: str, tmp_path: Path
) -> None:
    """§9.1 — la cible nommée est rendue telle quelle, même hors du répertoire."""
    elsewhere = tmp_path / "ailleurs"
    elsewhere.mkdir()
    target = elsewhere / name
    target.write_bytes(b"contenu")
    # The base directory is empty **and** elsewhere: a glob cannot find the file.
    connector = factory(str(tmp_path))

    candidates = await connector.discover(
        Query(filters={"location": str(target)})
    )

    assert len(candidates) == 1
    assert candidates[0].location == str(target)
    assert candidates[0].metadata["filename"] == name
    assert candidates[0].metadata["origin"] == "explicit_target"


@pytest.mark.parametrize(("factory", "name"), CONNECTORS, ids=IDS)
async def test_an_explicit_target_ignores_the_query_string(
    factory: type, name: str, tmp_path: Path
) -> None:
    """Une cible explicite n'a pas de fragment à filtrer : elle est rendue."""
    target = tmp_path / name
    target.write_bytes(b"contenu")
    connector = factory(str(tmp_path))

    candidates = await connector.discover(
        Query(query_string="aucun-rapport-avec-ce-fichier", filters={"location": str(target)})
    )

    assert [candidate.location for candidate in candidates] == [str(target)]


@pytest.mark.parametrize(("factory", "name"), CONNECTORS, ids=IDS)
async def test_an_s3_target_is_not_globbed(
    factory: type, name: str, tmp_path: Path
) -> None:
    """Un objet S3 n'est pas dans le répertoire de base : il est rendu quand même."""
    uri = f"s3://inis-artifacts/documents/REQ_1/{name}"
    connector = factory(str(tmp_path))

    candidates = await connector.discover(Query(filters={"location": uri}))

    assert len(candidates) == 1
    assert candidates[0].location == uri
    assert candidates[0].metadata["filename"] == name


@pytest.mark.parametrize(("factory", "name"), CONNECTORS, ids=IDS)
async def test_a_wrong_suffix_is_refused_by_name(
    factory: type, name: str, tmp_path: Path
) -> None:
    """§25.2 — une cible d'un autre type est un refus qui le dit, pas un vide."""
    wrong = tmp_path / "rapport.txt"
    wrong.write_text("pas le bon type", encoding="utf-8")
    connector = factory(str(tmp_path))

    with pytest.raises(ValidationError) as refusal:
        await connector.discover(Query(filters={"location": str(wrong)}))

    assert "rapport.txt" in str(refusal.value)
    assert "ne lit que" in str(refusal.value)


@pytest.mark.parametrize(("factory", "name"), CONNECTORS, ids=IDS)
async def test_the_glob_mode_is_unchanged(
    factory: type, name: str, tmp_path: Path
) -> None:
    """Non-régression : sans cible, la découverte reste celle du répertoire."""
    (tmp_path / name).write_bytes(b"contenu")
    (tmp_path / "ignore.txt").write_text("autre", encoding="utf-8")
    connector = factory(str(tmp_path))

    candidates = await connector.discover(Query(query_string="villes"))

    assert [candidate.metadata["filename"] for candidate in candidates] == [name]


@pytest.mark.parametrize(("factory", "name"), CONNECTORS, ids=IDS)
async def test_an_empty_location_filter_is_not_a_target(
    factory: type, name: str, tmp_path: Path
) -> None:
    """Un filtre vide n'est pas une cible : le mode glob reste actif."""
    (tmp_path / name).write_bytes(b"contenu")
    connector = factory(str(tmp_path))

    candidates = await connector.discover(Query(query_string="", filters={"location": "  "}))

    assert [candidate.metadata["filename"] for candidate in candidates] == [name]


@pytest.mark.parametrize(("factory", "name"), CONNECTORS, ids=IDS)
async def test_the_source_id_comes_from_the_file_name(
    factory: type, name: str, tmp_path: Path
) -> None:
    target = tmp_path / name
    target.write_bytes(b"contenu")
    connector = factory(str(tmp_path))

    candidates = await connector.discover(Query(filters={"location": str(target)}))

    assert candidates[0].source_id.endswith("-villes")


def test_a_query_needs_no_free_text_to_name_a_target() -> None:
    """Le plan écrit ``Query(filters={"location": …})`` : c'est un appel valide."""
    query = Query(filters={"location": "s3://bucket/key.csv"})

    assert query.query_string == ""
    assert query.filters == {"location": "s3://bucket/key.csv"}
