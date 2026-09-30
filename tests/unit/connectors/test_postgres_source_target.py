"""§7/§36.7 — une requête nomme une *source* PostgreSQL, jamais un DSN.

``constraints.source_preferences`` est le seul canal dont dispose une requête
pour dire « interroge ma base » (§7). Ce fichier verrouille ce qu'une entrée de
cette liste veut dire :

* ``postgres:<credential_ref>`` — la base détenue par cette entrée du vault
  §41.4 ; ``postgres:<credential_ref>#<table>`` — cette table précisément ;
* un DSN (``postgres://user:pw@host/db``) est refusé **par son nom** : la
  ressource qu'une requête peut choisir est une source, jamais un hôte, un
  utilisateur et un mot de passe ;
* une entrée ``postgres:`` malformée **lève** au lieu d'être ignorée : une faute
  de frappe qui disparaît deviendrait « aucune base n'a été nommée », et le
  pipeline chercherait sur le web des données que le demandeur détient déjà.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import Any

import pytest

from app.connectors.database.source_target import (
    PostgresSourceTarget,
    parse_target,
    select_target,
)
from app.core.errors import ValidationError

SECRET_DSN = "postgres://alice:s3cr3t@db.internal:5432/analytics"


class TestTheSourceAPreferenceNames:
    """§7 — ``postgres:<ref>[#table]`` décrit une source, et rien d'autre."""

    def test_a_vault_entry_is_read_without_a_table(self) -> None:
        target = parse_target("postgres:analytics")

        assert target == PostgresSourceTarget(credential_ref="analytics")
        assert target.table is None

    def test_the_table_can_be_named(self) -> None:
        target = parse_target("postgres:analytics#agents")

        assert target.credential_ref == "analytics"
        assert target.table == "agents"

    def test_the_prefix_is_case_insensitive(self) -> None:
        """Une préférence est écrite par un client : la casse ne change rien."""

        assert parse_target("POSTGRES:analytics#agents").table == "agents"

    def test_surrounding_whitespace_is_ignored(self) -> None:
        target = parse_target("  postgres:analytics#agents  ")

        assert target.table == "agents"

    def test_the_service_is_the_preference_that_named_it(self) -> None:
        """§11/§12.1 — le service consigné est la préférence, pas un DSN."""

        assert parse_target("postgres:analytics#agents").service == "postgres:analytics"

    def test_the_location_is_a_reference_not_a_connection(self) -> None:
        """§0.2/§41.4 — ``postgres://ref/table`` ne porte aucun secret."""

        location = parse_target("postgres:analytics#agents").location

        assert location == "postgres://analytics/agents"
        assert "@" not in location

    def test_a_source_without_a_table_still_has_a_location(self) -> None:
        assert parse_target("postgres:analytics").location == "postgres://analytics"

    def test_the_description_names_the_table(self) -> None:
        assert "agents" in parse_target("postgres:analytics#agents").describe()

    def test_the_description_says_when_no_table_is_named(self) -> None:
        assert "aucune table nommée" in parse_target("postgres:analytics").describe()

    def test_the_vault_entry_keeps_its_namespace(self) -> None:
        """Le nom d'entrée est celui du vault (§41.4), pas un hostname."""

class TestARefusedTarget:
    """§0.2/§19 — ce qu'une requête ne peut pas obtenir est refusé, et dit pourquoi."""

    def test_a_dsn_with_a_password_is_refused(self) -> None:
        with pytest.raises(ValidationError) as error:
            parse_target(SECRET_DSN)

        assert "s3cr3t" not in str(error.value)

    def test_a_dsn_without_credentials_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            parse_target("postgres://db.internal/analytics")

    def test_an_unknown_prefix_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="postgres:<credential_ref>"):
            parse_target("mysql:analytics")

    def test_an_empty_entry_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            parse_target("")

    def test_a_missing_vault_entry_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            parse_target("postgres:")

    def test_a_table_identifier_with_sql_is_refused(self) -> None:
        """L'identifiant est interpolé : il ne peut pas porter de SQL (§1.2, §19)."""

        with pytest.raises(ValidationError, match="nom de table PostgreSQL invalide"):
            parse_target("postgres:analytics#agents; DROP TABLE users")

    @pytest.mark.parametrize(
        "table", ["1agents", "agents-de-test", "agents--", "public.agents", "agents drop"]
    )
    def test_every_unquoted_identifier_outside_the_pattern_is_refused(
        self, table: str
    ) -> None:
        with pytest.raises(ValidationError):
            parse_target(f"postgres:analytics#{table}")


class TestSelectingTheSourceOfARequest:
    """§7 — une demande peut nommer des préférences web *et* une base."""

    def test_web_preferences_are_skipped(self) -> None:
        target = select_target(["web", "documents", "postgres:analytics#agents"])

        assert target == PostgresSourceTarget(credential_ref="analytics", table="agents")

    def test_no_preference_means_no_source(self) -> None:
        assert select_target(["web"]) is None

    def test_an_absent_list_means_no_source(self) -> None:
        assert select_target(None) is None
        assert select_target([]) is None

    def test_a_malformed_source_is_not_silently_dropped(self) -> None:
        """§0.2 — une préférence PostgreSQL illisible ne devient pas « aucune »."""

        with pytest.raises(ValidationError):
            select_target(["web", "postgres:"])

    def test_a_non_string_entry_is_skipped(self) -> None:
        """Le filtre porte sur la préférence ; ``None`` n'est pas une base."""

        assert select_target([None, ""]) is None


class TestTheTargetIsImmutable:
    """§5.3 — un plan qui relit la même préférence obtient la même cible."""

    def test_two_parses_of_one_preference_are_equal(self) -> None:
        assert parse_target("postgres:analytics#agents") == parse_target(
            "postgres:analytics#agents"
        )

    def test_a_target_cannot_be_mutated(self) -> None:
        target: Any = parse_target("postgres:analytics#agents")

        with pytest.raises(FrozenInstanceError):
            target.table = "other"
        assert parse_target("postgres:src/alpha#t").credential_ref == "src/alpha"