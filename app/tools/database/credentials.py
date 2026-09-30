"""§41.4/§36.7 — where the connection of ``postgres_query`` comes from.

A client names a **source**, never a connection string. The request carries
``postgres:<credential_ref>`` in ``constraints.source_preferences`` (§7) and the
secret material is read from the §41.4 vault; a DSN written in a request is
refused *by name*. Accepting it would turn "INIS queries your database" into
"whoever can call the API chooses which database INIS connects to, with which
password, and the audit trail records nothing".

The secret block is the one ``EnvVault``/``FileVault`` already store::

    {"host": …, "port": …, "database": …, "user": …, "password": …,
     "sslmode": "require"}

or a complete ``{"dsn": "postgresql://…"}`` when the deployment prefers one
opaque value. Nothing in this module logs or echoes a secret: the built DSN goes
to the engine factory and nowhere else, and the refusal messages name the
*entry*, never its content.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from typing import Any
from urllib.parse import quote

from app.core.errors import InfrastructureError, ValidationError
from app.security.vault.credential_vault import (
    CredentialNotFound,
    CredentialVault,
    EnvVault,
    FileVault,
    VaultError,
)

__all__ = [
    "CREDENTIAL_REF_PATTERN",
    "CREDENTIAL_REF_RULE",
    "DEFAULT_POSTGRES_PORT",
    "VAULT_FILE_ENV",
    "assert_credential_ref",
    "credential_env_var",
    "default_vault",
    "dsn_from_vault",
    "vault_file_path",
]

#: Accepted ``credential_ref``: a name, never a URL (no ``://``, no ``@``).
#: ``EnvVault`` sanitises ``/`` and ``.`` into ``_``, so both are accepted here.
CREDENTIAL_REF_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]*$")

#: The rule, stated once so every refusal says the same thing.
CREDENTIAL_REF_RULE = (
    "credential_ref doit nommer une entrée du vault (§41.4), jamais un DSN : "
    "un mot de passe dans la requête client n'est ni accepté ni journalisable"
)

#: Port used when the vault block does not carry one.
DEFAULT_POSTGRES_PORT = 5432

#: Environment variable naming the encrypted vault file (``FileVault``).
VAULT_FILE_ENV = "INIS_VAULT_FILE"


def vault_file_path() -> str | None:
    """Return the configured vault file, or ``None`` (environment vault)."""
    raw = os.getenv(VAULT_FILE_ENV)
    return raw.strip() if raw and raw.strip() else None


def default_vault() -> CredentialVault:
    """Return the deployment's vault (§41.4).

    ``INIS_VAULT_FILE`` selects the encrypted ``FileVault``; otherwise the
    ``EnvVault`` is used, which reads ``INIS_CRED_<REF>`` as JSON. Neither
    backend persists a secret in the database.
    """
    path = vault_file_path()
    if path:
        return FileVault(path)
    return EnvVault()


def credential_env_var(credential_ref: str) -> str:
    """Return the environment variable holding *credential_ref*'s secret.

    Mirrors ``EnvVault`` sanitisation exactly, so the message shown to an
    operator names the variable that will actually be read.
    """
    return f"INIS_CRED_{credential_ref.replace('.', '_').replace('/', '_').upper()}"


def assert_credential_ref(credential_ref: Any) -> str:
    """Return *credential_ref* when it names a vault entry.

    Raises:
        ValidationError: When it is empty, contains a URL/credentials marker
            (``://``, ``@``) or is not a plain name.
    """
    if not isinstance(credential_ref, str) or not credential_ref.strip():
        raise ValidationError("credential_ref must be a non-empty string")
    text = credential_ref.strip()
    if "://" in text or "@" in text:
        raise ValidationError(f"{CREDENTIAL_REF_RULE} (requête reçue : refusée)")
    if not CREDENTIAL_REF_PATTERN.match(text):
        raise ValidationError(f"{CREDENTIAL_REF_RULE} (forme invalide)")
    return text


def _dsn_from_secret(credential_ref: str, secret: Any) -> str:
    """Build the asyncpg DSN of one vault block."""
    if not isinstance(secret, Mapping):
        raise InfrastructureError(
            f"bloc vault illisible pour '{credential_ref}' : un objet JSON est attendu (§41.4)"
        )

    direct = secret.get("dsn") or secret.get("url") or secret.get("connection_string")
    if direct:
        dsn = str(direct)
        if not dsn.startswith(("postgresql://", "postgres://", "postgresql+asyncpg://")):
            raise InfrastructureError(
                f"le DSN du vault pour '{credential_ref}' n'est pas PostgreSQL (§41.4)"
            )
        return dsn

    host = str(secret.get("host") or "").strip()
    database = str(secret.get("database") or secret.get("dbname") or "").strip()
    missing = [name for name, value in (("host", host), ("database", database)) if not value]
    if missing:
        raise InfrastructureError(
            f"bloc vault incomplet pour '{credential_ref}' : "
            f"{', '.join(missing)} manquant(s) (§41.4)"
        )

    raw_port = secret.get("port")
    try:
        port = int(raw_port) if raw_port not in (None, "") else DEFAULT_POSTGRES_PORT
    except (TypeError, ValueError) as exc:
        raise InfrastructureError(
            f"port invalide dans le bloc vault de '{credential_ref}' (§41.4)"
        ) from exc
    if not 0 < port < 65_536:
        raise InfrastructureError(
            f"port hors bornes dans le bloc vault de '{credential_ref}' (§41.4)"
        )

    user = str(secret.get("user") or secret.get("username") or "postgres")
    password = secret.get("password")
    credentials = quote(user, safe="")
    if password:
        credentials = f"{credentials}:{quote(str(password), safe='')}"
    dsn = f"postgresql+asyncpg://{credentials}@{host}:{port}/{quote(database, safe='')}"

    sslmode = str(secret.get("sslmode") or "").strip().lower()
    if sslmode and sslmode != "disable":
        dsn = f"{dsn}?ssl={'verify-ca' if sslmode == 'verify-ca' else 'require'}"
    return dsn


def dsn_from_vault(credential_ref: Any, *, vault: CredentialVault | None = None) -> str:
    """Return the PostgreSQL DSN of *credential_ref*, read from the vault.

    Args:
        credential_ref: Name of the vault entry (never a DSN).
        vault: Vault to read; the deployment's vault when omitted.

    Returns:
        A ``postgresql+asyncpg://`` connection string. It is never logged, and it
        never comes from the request.

    Raises:
        ValidationError: When *credential_ref* is not a plain name.
        InfrastructureError: When the entry is absent, unreadable, or does not
            describe a usable PostgreSQL connection.
    """
    ref = assert_credential_ref(credential_ref)
    active = vault if vault is not None else default_vault()
    try:
        secret = active.get(ref)
    except CredentialNotFound as exc:
        raise InfrastructureError(
            f"identifiants absents du vault pour '{ref}' (§41.4) : poser "
            f"{credential_env_var(ref)} (JSON) ou {VAULT_FILE_ENV}. Aucune connexion "
            "n'est tentée avec un DSN venu de la requête."
        ) from exc
    except VaultError as exc:
        raise InfrastructureError(f"vault illisible pour '{ref}' (§41.4) : {exc}") from exc
    return _dsn_from_secret(ref, secret)