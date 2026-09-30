"""Tests of the hermetic-by-default test environment policy (§33.3).

The suite must produce the same result on a bare machine and on a workstation
whose ``.env`` points at a real PostgreSQL, a real Redis and a billed LLM key.
:mod:`tests.env_policy` is the rule that guarantees it; these tests are its
contract, so a future variable added to ``.env`` cannot silently re-introduce a
dependency on the machine.
"""

from __future__ import annotations

from tests.env_policy import (
    CONFIGURATION_VARIABLES,
    LIVE_LLM_OPT_IN,
    LIVE_VARIABLES,
    SECURITY_VARIABLES,
    SERVICE_VARIABLES,
    STACK_OPT_IN,
    enforce_hermetic_environment,
)


def _full_environment() -> dict[str, str]:
    """A process environment polluted by every variable of the policy."""
    environ = {
        name: "value"
        for name in (
            *SERVICE_VARIABLES,
            *SECURITY_VARIABLES,
            *LIVE_VARIABLES,
            *CONFIGURATION_VARIABLES,
        )
    }
    environ["ENVIRONMENT"] = "development"
    return environ


class TestDefaultPolicy:
    """By default, nothing that changes behaviour survives."""

    def test_services_security_live_and_configuration_are_removed(self) -> None:
        environ = _full_environment()
        removed = enforce_hermetic_environment(environ)
        assert set(environ) == {"ENVIRONMENT"}
        assert set(removed["services"]) == set(SERVICE_VARIABLES)
        assert set(removed["security"]) == set(SECURITY_VARIABLES)
        assert set(removed["live"]) == set(LIVE_VARIABLES)
        assert set(removed["configuration"]) == set(CONFIGURATION_VARIABLES)

    def test_unrelated_variables_are_kept(self) -> None:
        environ = {"ENVIRONMENT": "development", "LOG_LEVEL": "DEBUG"}
        enforce_hermetic_environment(environ)
        assert environ == {"ENVIRONMENT": "development", "LOG_LEVEL": "DEBUG"}

    def test_absent_variables_are_not_reported(self) -> None:
        removed = enforce_hermetic_environment({})
        assert removed == {"services": [], "security": [], "live": [], "configuration": []}


class TestOptIns:
    """Two explicit switches exist, and only two."""

    def test_live_llm_keeps_only_the_llm_key(self) -> None:
        environ = _full_environment()
        environ[LIVE_LLM_OPT_IN] = "1"
        removed = enforce_hermetic_environment(environ)
        assert "LLM_API_KEY" in environ
        assert "SERPER_API_KEY" not in environ
        assert "BRAVE_API_KEY" not in environ
        assert removed["live"] == ["SERPER_API_KEY", "BRAVE_API_KEY"]

    def test_live_llm_does_not_keep_the_services(self) -> None:
        environ = _full_environment()
        environ[LIVE_LLM_OPT_IN] = "1"
        enforce_hermetic_environment(environ)
        assert "INIS_DATABASE_URL" not in environ

    def test_stack_opt_in_keeps_everything(self) -> None:
        environ = _full_environment()
        environ[STACK_OPT_IN] = "1"
        removed = enforce_hermetic_environment(environ)
        assert removed == {"services": [], "security": [], "live": [], "configuration": []}
        assert "INIS_DATABASE_URL" in environ
        assert "LLM_API_KEY" in environ

    def test_opt_in_flags_must_be_truthy(self) -> None:
        environ = _full_environment()
        environ[STACK_OPT_IN] = "no"
        environ[LIVE_LLM_OPT_IN] = "0"
        enforce_hermetic_environment(environ)
        assert "INIS_DATABASE_URL" not in environ
        assert "LLM_API_KEY" not in environ
