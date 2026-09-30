"""§21/§36.7/§41.4 — ``postgres_query`` is read-only and uses the vault (§33).

Two contracts are locked here:

* a statement that is not a single ``SELECT``/``WITH`` never reaches a
  connection, and the query itself runs in a ``READ ONLY`` transaction bounded
  by a ``statement_timeout`` (§1.2, §41.13);
* the database is chosen by a §41.4 **vault entry**, never by a DSN written in
  the request: ``postgres://user:secret@host/db`` in ``credential_ref`` is
  refused by name, and the refusal does not echo it.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any, Self

import pytest

#: ``app.tools.database`` re-exports the *function* under the module's name, so the
#: module is fetched from ``sys.modules`` by name instead of by attribute access.
query_module = importlib.import_module("app.tools.database.postgres_query")

from app.core.errors import InfrastructureError, ValidationError
from app.security.vault.credential_vault import EnvVault, FileVault
from app.tools.database import credentials as credentials_module
from app.tools.database.credentials import (
    assert_credential_ref,
    credential_env_var,
    default_vault,
    dsn_from_vault,
)
from app.tools.database.postgres_query import (
    DEFAULT_STATEMENT_TIMEOUT_MS,
    MAX_STATEMENT_TIMEOUT_MS,
    STATEMENT_TIMEOUT_ENV,
    assert_read_only,
    effective_statement_timeout_ms,
    postgres_query,
)

SECRET_DSN = "postgresql://alice:s3cr3t@db.internal:5432/analytics"


class FakeResult:
    """Minimal SQLAlchemy result surface (``mappings().all()``)."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def mappings(self) -> Self:
        return self

    def all(self) -> list[dict[str, Any]]:
        return self._rows


class FakeConnection:
    """Async connection recording every statement it is asked to run."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows
        self.executions: list[tuple[str, Any]] = []

    async def execute(self, statement: Any, parameters: Any = None) -> FakeResult:
        self.executions.append((str(statement), parameters))
        return FakeResult(self._rows)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None


class FakeEngine:
    """Async engine double exposing ``begin()`` only (read-only path)."""

    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self.connection = FakeConnection(rows or [])
        self.begun = 0
        self.connected = 0

    def begin(self) -> FakeConnection:
        self.begun += 1
        return self.connection

    def connect(self) -> FakeConnection:  # pragma: no cover - must not be used
        self.connected += 1
        return self.connection


def _capturing_resolver(captured: list[str], engine: FakeEngine) -> Any:
    """Return a ``resolve_engine`` replacement recording the URL it is given."""

    def _resolve(
        engine_arg: Any, connection_string: str | None, *, component: str
    ) -> FakeEngine:
        captured.append(str(connection_string))
        return engine_arg if engine_arg is not None else engine

    return _resolve


@pytest.fixture()
def analytics_vault() -> EnvVault:
    """A vault holding one PostgreSQL source named ``analytics``."""
    vault = EnvVault({})
    vault.set(
        "analytics",
        {
            "host": "db.internal",
            "port": 5432,
            "database": "analytics",
            "user": "alice",
            "password": "s3cr3t",
        },
    )
    return vault


class TestReadOnlyStatements:
    """The textual guard: only one ``SELECT``/``WITH`` may reach the engine."""

    @pytest.mark.parametrize(
        "sql",
        [
            "UPDATE agents SET name = 'planner'",
            "DELETE FROM agents",
            "INSERT INTO agents (agent_id) VALUES ('AG_1')",
            "DROP TABLE agents",
            "ALTER TABLE agents ADD COLUMN note text",
            "CREATE TABLE tmp (id int)",
            "TRUNCATE agents",
            "GRANT ALL ON agents TO public",
            "VACUUM agents",
            "WITH x AS (DELETE FROM agents RETURNING *) SELECT * FROM x",
            "SELECT 1; DROP TABLE agents",
            "",
            "   ",
        ],
    )
    def test_a_write_or_a_stacked_statement_is_refused(self, sql: str) -> None:
        with pytest.raises(ValidationError):
            assert_read_only(sql)

    def test_a_comment_cannot_smuggle_a_write(self) -> None:
        with pytest.raises(ValidationError):
            assert_read_only("/* SELECT */ DELETE FROM agents")

    def test_select_and_with_are_accepted(self) -> None:
        assert assert_read_only("SELECT 1;") == "SELECT 1"
        assert assert_read_only("with recent as (select 1) select * from recent") == (
            "with recent as (select 1) select * from recent"
        )

    @pytest.mark.asyncio
    async def test_a_refused_statement_never_opens_a_connection(self) -> None:
        """§1.2 — the refusal happens before any connection is taken."""
        engine = FakeEngine()

        with pytest.raises(ValidationError):
            await postgres_query("DELETE FROM agents", engine=engine)

        assert engine.begun == 0
        assert engine.connected == 0


class TestQueryExecution:
    """What the tool actually sends to PostgreSQL."""

    @pytest.mark.asyncio
    async def test_a_select_returns_its_rows_with_bound_parameters(self) -> None:
        engine = FakeEngine([{"table_name": "agents"}])

        rows = await postgres_query(
            "SELECT table_name FROM information_schema.tables WHERE table_name LIKE :pattern",
            {"pattern": "%a%"},
            engine=engine,
        )

        statement, parameters = engine.connection.executions[-1]
        assert statement.endswith("LIMIT 1000")
        assert parameters == {"pattern": "%a%"}
        assert rows == [{"table_name": "agents"}]

    @pytest.mark.asyncio
    async def test_the_transaction_is_read_only_and_time_bounded(self) -> None:
        """§41.13 — PostgreSQL itself refuses a write, and the time is boxed."""
        engine = FakeEngine()

        await postgres_query("SELECT 1", engine=engine)

        statements = [statement for statement, _ in engine.connection.executions]
        assert statements == [
            "SET TRANSACTION READ ONLY",
            f"SET LOCAL statement_timeout = {DEFAULT_STATEMENT_TIMEOUT_MS}",
            "SELECT 1 LIMIT 1000",
        ]

    @pytest.mark.asyncio
    async def test_the_timeout_can_be_shortened_but_not_extended(self) -> None:
        engine = FakeEngine()

        await postgres_query("SELECT 1", engine=engine, statement_timeout_ms=250)
        assert engine.connection.executions[1][0] == "SET LOCAL statement_timeout = 250"

        await postgres_query("SELECT 1", engine=engine, statement_timeout_ms=10**9)
        assert engine.connection.executions[-2][0] == (
            f"SET LOCAL statement_timeout = {MAX_STATEMENT_TIMEOUT_MS}"
        )

    @pytest.mark.asyncio
    async def test_a_statement_that_already_limits_itself_is_left_alone(self) -> None:
        engine = FakeEngine()

        await postgres_query("SELECT * FROM agents LIMIT 5", engine=engine)

        assert engine.connection.executions[-1][0] == "SELECT * FROM agents LIMIT 5"

    @pytest.mark.asyncio
    async def test_the_bounds_must_be_positive(self) -> None:
        engine = FakeEngine()

        with pytest.raises(ValidationError, match="max_rows"):
            await postgres_query("SELECT 1", engine=engine, max_rows=0)
        with pytest.raises(ValidationError, match="statement_timeout_ms"):
            await postgres_query("SELECT 1", engine=engine, statement_timeout_ms=0)

        assert engine.begun == 0

    def test_an_unusable_environment_value_never_means_unlimited(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(STATEMENT_TIMEOUT_ENV, "not-a-number")
        assert effective_statement_timeout_ms() == DEFAULT_STATEMENT_TIMEOUT_MS

        monkeypatch.setenv(STATEMENT_TIMEOUT_ENV, "0")
        assert effective_statement_timeout_ms() == DEFAULT_STATEMENT_TIMEOUT_MS

        monkeypatch.setenv(STATEMENT_TIMEOUT_ENV, "900")
        assert effective_statement_timeout_ms() == 900

        monkeypatch.setenv(STATEMENT_TIMEOUT_ENV, str(MAX_STATEMENT_TIMEOUT_MS * 10))
        assert effective_statement_timeout_ms() == MAX_STATEMENT_TIMEOUT_MS


class TestVaultCredentials:
    """§41.4 — the database is named by a vault entry, never by a DSN."""

    def test_the_ref_must_name_an_entry(self) -> None:
        for value in ("", "   ", None, 42, "postgres://u:p@h/db", "alice:pw@db", "a b"):
            with pytest.raises(ValidationError):
                assert_credential_ref(value)

        assert assert_credential_ref(" analytics ") == "analytics"
        assert assert_credential_ref("pg.analytics-1") == "pg.analytics-1"

    def test_a_dsn_in_the_ref_is_refused_without_echoing_it(self) -> None:
        with pytest.raises(ValidationError) as error:
            assert_credential_ref(SECRET_DSN)

        assert "s3cr3t" not in str(error.value)
        assert "db.internal" not in str(error.value)

    def test_the_dsn_is_built_from_the_vault_block(self, analytics_vault: EnvVault) -> None:
        dsn = dsn_from_vault("analytics", vault=analytics_vault)

        assert dsn == "postgresql+asyncpg://alice:s3cr3t@db.internal:5432/analytics"

    def test_a_missing_port_or_password_is_not_an_error(self) -> None:
        vault = EnvVault({})
        vault.set("plain", {"host": "h", "database": "d"})

        assert dsn_from_vault("plain", vault=vault) == (
            "postgresql+asyncpg://postgres@h:5432/d"
        )

    def test_ssl_requirement_is_carried_to_the_driver(self) -> None:
        vault = EnvVault({})
        vault.set("secure", {"host": "h", "database": "d", "sslmode": "require"})

        assert dsn_from_vault("secure", vault=vault).endswith("?ssl=require")

    def test_a_vault_block_may_carry_one_opaque_dsn(self) -> None:
        vault = EnvVault({})
        vault.set("opaque", {"dsn": "postgresql://alice:pw@h:5432/d"})

        assert dsn_from_vault("opaque", vault=vault) == "postgresql://alice:pw@h:5432/d"

    def test_a_non_postgres_dsn_in_the_vault_is_refused(self) -> None:
        vault = EnvVault({})
        vault.set("mysql", {"dsn": "mysql://alice@h/d"})

        with pytest.raises(InfrastructureError, match="pas PostgreSQL"):
            dsn_from_vault("mysql", vault=vault)

    def test_an_incomplete_block_names_what_is_missing(self) -> None:
        vault = EnvVault({})
        vault.set("partial", {"host": "h"})

        with pytest.raises(InfrastructureError, match="database"):
            dsn_from_vault("partial", vault=vault)

    def test_an_unusable_port_is_refused(self) -> None:
        vault = EnvVault({})
        vault.set("bad-port", {"host": "h", "database": "d", "port": "abc"})

        with pytest.raises(InfrastructureError, match="port invalide"):
            dsn_from_vault("bad-port", vault=vault)

    def test_an_absent_entry_names_the_variable_to_set(self) -> None:
        with pytest.raises(InfrastructureError) as error:
            dsn_from_vault("missing", vault=EnvVault({}))

        assert credential_env_var("missing") == "INIS_CRED_MISSING"
        assert "INIS_CRED_MISSING" in str(error.value)

    def test_the_env_var_name_mirrors_the_vault_sanitisation(self) -> None:
        vault = EnvVault({"INIS_CRED_SRC_ALPHA": '{"host": "h", "database": "d"}'})

        assert credential_env_var("src/alpha") == "INIS_CRED_SRC_ALPHA"
        assert dsn_from_vault("src/alpha", vault=vault).startswith("postgresql+asyncpg://")

    def test_the_default_vault_follows_the_configuration(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv(credentials_module.VAULT_FILE_ENV, raising=False)
        assert isinstance(default_vault(), EnvVault)

        monkeypatch.setenv(credentials_module.VAULT_FILE_ENV, str(tmp_path / "vault.json"))
        monkeypatch.setenv("INIS_VAULT_KEY", "unit-test-master-key")
        assert isinstance(default_vault(), FileVault)

    @pytest.mark.asyncio
    async def test_the_query_runs_on_the_vault_dsn(
        self, analytics_vault: EnvVault, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The connection string used is the vault's, not anything from a caller."""
        engine = FakeEngine()
        captured: list[str] = []

        monkeypatch.setattr(query_module, "resolve_engine", _capturing_resolver(captured, engine))

        rows = await postgres_query(
            "SELECT 1", credential_ref="analytics", vault=analytics_vault
        )

        assert captured == ["postgresql+asyncpg://alice:s3cr3t@db.internal:5432/analytics"]
        assert rows == []

    @pytest.mark.asyncio
    async def test_a_request_cannot_choose_its_database(self, analytics_vault: EnvVault) -> None:
        engine = FakeEngine()

        with pytest.raises(ValidationError):
            await postgres_query("SELECT 1", credential_ref=SECRET_DSN, vault=analytics_vault)

        assert engine.begun == 0