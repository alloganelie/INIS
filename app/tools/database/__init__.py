"""Database tools per §21: ``postgres_query`` (read-only).

The connection a query runs on comes from the §41.4 vault
(:mod:`app.tools.database.credentials`): a request names a source, never a DSN.
"""

from app.tools.database.credentials import (
    assert_credential_ref,
    credential_env_var,
    default_vault,
    dsn_from_vault,
)
from app.tools.database.postgres_query import (
    DEFAULT_MAX_ROWS,
    DEFAULT_STATEMENT_TIMEOUT_MS,
    MAX_STATEMENT_TIMEOUT_MS,
    assert_read_only,
    effective_statement_timeout_ms,
    postgres_query,
)

__all__ = [
    "DEFAULT_MAX_ROWS",
    "DEFAULT_STATEMENT_TIMEOUT_MS",
    "MAX_STATEMENT_TIMEOUT_MS",
    "assert_credential_ref",
    "assert_read_only",
    "credential_env_var",
    "default_vault",
    "dsn_from_vault",
    "effective_statement_timeout_ms",
    "postgres_query",
]
