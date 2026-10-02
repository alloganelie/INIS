"""§13.2 — une cellule qui ne tient pas dans sa colonne est isolée, pas absorbée.

Le constat laissé `[~]` par le lot L5 était précis : « sur cette chaîne, une
cellule de CSV qui ne tient pas dans sa colonne (`beaucoup` dans une colonne
numérique) n'est pas isolée : le lecteur stocke les cellules en texte, la colonne
reste homogène (cohérence 1.0, schéma inféré `string`) ». Le fichier passe par un
**vrai** `load_csv`, puis par les contrôles §13.2 réellement appelés.

Ce qui est prouvé ici :

* la ligne **et** la colonne de la cellule fautive sont nommées ;
* rien n'est inventé : la valeur stockée n'est ni corrigée ni remplacée ;
* les autres lignes valides ne sont pas détruites ;
* une colonne sans majorité stricte n'est pas arbitrée (aucune violation) ;
* une colonne homogène ne produit aucune violation (aucune régression).
"""

from __future__ import annotations

import asyncio

from app.tools.files.csv_reader import load_csv
from app.tools.files.dataset_inspector import inspect_schema, validate_schema

DIRTY_CSV = (
    "city,population\n"
    "Paris,2145906\n"
    "Lyon,522250\n"
    "Nice,beaucoup\n"  # une colonne numérique partout ailleurs
    "Nantes,320732\n"
    "Lille,\n"  # valeur manquante (aucune invention de valeur)
)

CLEAN_CSV = "city,population\nParis,2145906\nLyon,522250\nNice,342522\n"


def _load(tmp_path, content: str) -> tuple[dict, list[dict]]:
    """Write the payload to disk and read it with the **real** CSV reader."""
    path = tmp_path / "payload.csv"
    path.write_text(content, encoding="utf-8")
    dataset, rows = load_csv(str(path), source_id="SRC_01M3Q0000000000000000000AB")
    return dataset, rows


class TestAnOutOfTypeCellIsIsolated:
    """La cellule aberrante est nommée, et rien n'est inventé."""

    def test_the_row_and_the_column_are_named(self, tmp_path) -> None:
        _, rows = _load(tmp_path, DIRTY_CSV)
        schema = asyncio.run(inspect_schema(rows))
        result = asyncio.run(validate_schema(rows, schema))

        failures = [item for item in result.violations if item.observed == "string"]
        assert failures, f"la cellule « beaucoup » doit être isolée : {result.violations}"
        assert failures[0].field == "population", "la colonne fautive est nommée"
        assert failures[0].expected == "integer", "le type attendu est celui de la colonne"
        assert rows[failures[0].row_index]["city"] == "Nice", (
            "l'index de ligne permet de retrouver la cellule source"
        )

    def test_the_stored_value_is_never_modified(self, tmp_path) -> None:
        """§0.2 — aucune valeur n'est corrigée ni remplacée pour faire passer."""
        _, rows = _load(tmp_path, DIRTY_CSV)
        original = [dict(row) for row in rows]

        asyncio.run(validate_schema(rows, asyncio.run(inspect_schema(rows))))

        assert rows == original, "le contrôle ne réécrit aucune cellule"
        assert any(row["population"] == "beaucoup" for row in rows), (
            "la valeur fautive reste telle qu'elle a été lue"
        )

    def test_the_valid_rows_survive(self, tmp_path) -> None:
        """Une anomalie ne détruit pas les lignes valides."""
        _, rows = _load(tmp_path, DIRTY_CSV)
        result = asyncio.run(validate_schema(rows, asyncio.run(inspect_schema(rows))))

        assert result.checked_rows == len(rows) == 5
        numeric_rows = [row["population"] for row in rows if str(row["population"]).isdigit()]
        assert len(numeric_rows) == 3, "les trois lignes numériques restent intactes"

    def test_the_missing_value_stays_a_missing_value(self, tmp_path) -> None:
        """Une cellule vide reste ``null`` : elle n'est pas confondue avec du texte."""
        _, rows = _load(tmp_path, DIRTY_CSV)
        result = asyncio.run(validate_schema(rows, asyncio.run(inspect_schema(rows))))

        nulls = [item for item in result.violations if item.observed == "null"]
        assert nulls, "la cellule vide est signalée comme manquante, pas comme texte"
        assert nulls[0].field == "population"


class TestAColumnWithoutAMajorityIsNotArbitrated:
    """Une colonne sans majorité stricte ne produit aucune violation inventée."""

    def test_an_even_split_is_left_alone(self) -> None:
        rows = [
            {"valeur": "12"},
            {"valeur": "beaucoup"},
        ]
        result = asyncio.run(validate_schema(rows, asyncio.run(inspect_schema(rows))))

        assert result.violations == [], (
            "deux natures à égalité : rien ne dit laquelle est la bonne"
        )

    def test_a_column_of_text_is_not_a_violation(self) -> None:
        rows = [{"nom": "Paris"}, {"nom": "Lyon"}, {"nom": "Nice"}]
        result = asyncio.run(validate_schema(rows, asyncio.run(inspect_schema(rows))))

        assert result.valid is True
        assert result.violations == []


class TestACleanFileStaysClean:
    """Aucune régression : un fichier propre ne produit aucun défaut."""

    def test_a_clean_csv_is_valid(self, tmp_path) -> None:
        _, rows = _load(tmp_path, CLEAN_CSV)
        result = asyncio.run(validate_schema(rows, asyncio.run(inspect_schema(rows))))

        assert result.valid is True, f"aucune violation attendue : {result.violations}"
        assert result.violations == []

    def test_a_decimal_column_accepts_integers(self) -> None:
        """``number`` accueille ``integer`` : un entier est un nombre."""
        rows = [{"montant": "12.5"}, {"montant": "7"}, {"montant": "3.25"}]
        result = asyncio.run(validate_schema(rows, asyncio.run(inspect_schema(rows))))

        assert result.violations == [], f"un entier n'est pas un défaut ici : {result.violations}"