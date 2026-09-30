"""§7/§36.7 — a request names the PostgreSQL source it wants INIS to query.

The only channel a request has for "interroge ma base" is
``constraints.source_preferences`` (§7), and this module defines what an entry of
that list means:

* ``postgres:<credential_ref>`` — query the database held in that §41.4 vault
  entry;
* ``postgres:<credential_ref>#<table>`` — read exactly that table.

Nothing else is accepted. In particular a DSN is refused by name: the resource
the request may choose is a *source*, never a host, a user and a password.

A malformed ``postgres:`` entry raises instead of being ignored — an entry that
silently disappears would turn a typo into "no database was named", and the
pipeline would then search the web for data the requester already owns.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from app.core.errors import ValidationError
from app.tools.database.credentials import assert_credential_ref

__all__ = [
    "SOURCE_PREFIX",
    "TABLE_SEPARATOR",
    "PostgresSourceTarget",
    "parse_target",
    "select_target",
]

#: Prefix marking a PostgreSQL source preference (``postgres:analytics#agents``).
SOURCE_PREFIX = "postgres:"

#: Separator between the vault entry and the table to read.
TABLE_SEPARATOR = "#"

#: PostgreSQL identifiers interpolated without quoting must match this pattern.
TABLE_PATTERN = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


@dataclass(frozen=True)
class PostgresSourceTarget:
    """One PostgreSQL source named by a request (§7, §36.7)."""

    credential_ref: str
    table: str | None = None

    @property
    def service(self) -> str:
        """Return the preference that named this source (``postgres:<ref>``)."""
        return f"{SOURCE_PREFIX}{self.credential_ref}"

    @property
    def location(self) -> str:
        """Return the location of the material, without any secret.

        A ``postgres://`` URL here is a *reference*, never a DSN: it carries no
        user and no password — ``postgres://analytics/agents`` says which vault
        entry was read, which is what §11 provenance needs.
        """
        return f"postgres://{self.credential_ref}/{self.table or ''}".rstrip("/")

    def describe(self) -> str:
        """Return the sentence a delivery uses to name this source."""
        if self.table:
            return f"base PostgreSQL « {self.credential_ref} », table {self.table}"
        return f"base PostgreSQL « {self.credential_ref} » (aucune table nommée)"


def parse_target(entry: Any) -> PostgresSourceTarget:
    """Return the target described by one ``source_preferences`` entry.

    Args:
        entry: One entry of ``constraints.source_preferences``.

    Returns:
        The parsed target.

    Raises:
        ValidationError: When the entry does not start with ``postgres:``, names
            no vault entry, carries a DSN, or names an unsafe table identifier.
    """
    text = str(entry or "").strip()
    if not text.lower().startswith(SOURCE_PREFIX):
        raise ValidationError(
            f"une préférence de source PostgreSQL s'écrit « postgres:<credential_ref>"
            f"[#table] » (§7) : reçu {text!r}"
        )
    body = text[len(SOURCE_PREFIX) :].strip()
    reference, _, table = body.partition(TABLE_SEPARATOR)
    credential_ref = assert_credential_ref(reference.strip())

    table = table.strip()
    if table:
        if not TABLE_PATTERN.match(table):
            raise ValidationError(
                f"nom de table PostgreSQL invalide : {table!r} (les identifiants "
                "interpolés sans guillemets doivent correspondre à "
                "^[a-zA-Z_][a-zA-Z0-9_]*$)"
            )
        return PostgresSourceTarget(credential_ref=credential_ref, table=table)
    return PostgresSourceTarget(credential_ref=credential_ref)


def select_target(entries: Iterable[Any] | None) -> PostgresSourceTarget | None:
    """Return the PostgreSQL source of *entries*, or ``None`` when none is named.

    Non-``postgres:`` entries are web preferences and are skipped. A *malformed*
    ``postgres:`` entry raises: it must never be silently dropped.
    """
    for entry in entries or ():
        if str(entry or "").strip().lower().startswith(SOURCE_PREFIX):
            return parse_target(entry)
    return None