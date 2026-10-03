"""Hermetic-by-default policy for the test environment (§33).

``.env`` is loaded for the whole process (``app/__init__.py``), which is what a
developer expects: one file, read once. Determinism is the other half of the
contract — a suite whose result depends on the machine's ``.env`` is not a
suite (§33.3). So the values that change *behaviour* are removed before the
first test module is imported:

* **services** (PostgreSQL, Redis, RabbitMQ, S3): ``tests/containers.py`` starts
  its own containers and hands their URL to each test through ``db_url`` /
  ``redis_url``. Keeping the developer's URLs would make the suite write into
  their development database;
* **security** (``INIS_AUTH_ENABLED``, ``JWT_SECRET``, …): a test that expects
  ``401`` must say so explicitly, not inherit it from a local file;
* **live providers** (``LLM_API_KEY``, ``SERPER_API_KEY``, ``BRAVE_API_KEY``):
  they cost money and are not deterministic. ``INIS_LIVE_LLM=1`` opts the LLM
  key back in (the documented switch of ``tests/integration/test_llm_live_provider.py``);
* **configuration** (``LLM_MODEL_DEFAULT``, ``LLM_MODEL_FALLBACKS``, …): a test
  asserts the *documented* default routing, not the model a workstation
  configured. This group exists because installing ``.env`` support broke seven
  routing tests on the first run: the failure is the proof that the leak was
  real, and the group is the fix.

:data:`CLASSIFIED_VARIABLES` lists every variable the policy knows about, and
``tests/unit/core/test_env_example_matches_code.py`` fails when ``.env.example``
documents one that no group classifies — so the policy cannot silently fall
behind the configuration surface.

Two explicit opt-ins exist for real-stack runs:

* ``INIS_LIVE_LLM=1`` — keep ``LLM_API_KEY`` so a real provider call is served;
* ``INIS_TEST_USE_ENV=1`` — keep everything, i.e. run the suite against the
  developer's ``docker compose`` stack. Used when proving persistence end to
  end (``tests/integration/test_postgres_real.py``), never in CI.
"""

from __future__ import annotations

import os
from collections.abc import MutableMapping
from pathlib import Path

from app.core.env import bootstrap_environment

__all__ = [
    "LIVE_LLM_OPT_IN",
    "LIVE_VARIABLES",
    "SECURITY_VARIABLES",
    "SERVICE_VARIABLES",
    "STACK_OPT_IN",
    "enforce_hermetic_environment",
    "load_environment",
]

#: Container/endpoint URLs and pools: always provided by the test session itself.
SERVICE_VARIABLES = (
    "INIS_DATABASE_URL",
    "DATABASE_URL",
    "INIS_NULL_POOL",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_DB",
    "REDIS_URL",
    "AMQP_URL",
    "INIS_BROKER_URL",
    "RABBITMQ_USER",
    "RABBITMQ_PASSWORD",
    "S3_ENDPOINT",
    "S3_ACCESS_KEY",
    "S3_SECRET_KEY",
    "S3_BUCKET",
    "S3_REGION",
    "S3_USE_SSL",
)

#: Variables that flip an authenticated / rate-limited / vaulted code path.
SECURITY_VARIABLES = (
    "INIS_AUTH_ENABLED",
    "INIS_API_KEY",
    "INIS_RATE_LIMIT_ENABLED",
    "ACCESS_TOKEN_TTL_SECONDS",
    "JWT_SECRET",
    "INIS_VAULT_KEY",
    "INIS_CRED_SRC_ALPHA",
    "INIS_RESUME_SECRET",
)

#: Real providers: a network call must be an opt-in, never an inheritance.
LIVE_VARIABLES = ("LLM_API_KEY", "SERPER_API_KEY", "BRAVE_API_KEY")

#: Behaviour-changing configuration: a test asserts the *documented* default,
#: never the model, bucket or endpoint picked on someone's workstation.
CONFIGURATION_VARIABLES = (
    "LLM_BASE_URL",
    "LLM_MODEL_DEFAULT",
    "LLM_MODEL",
    "LLM_MODEL_FALLBACKS",
    "LLM_RETRY_ATTEMPTS",
    "LLM_PROBE_MAX_TOKENS",
    "LLM_EMBEDDING_MODEL",
    "LLM_EMBEDDING_BATCH",
    "SERPER_ENDPOINT",
    "RATE_LIMIT_RPM",
    "REDIS_PREFIX",
    "REDIS_TTL_SECONDS",
    "CORS_ORIGINS",
    "GIT_COMMIT",
    "COMMIT_SHA",
    "INIS_GIT_SHA",
    "INIS_BUILT_AT",
)

#: Deliberately *not* hermetic: these describe the machine, not the behaviour,
#: or they are the opt-in flags themselves.
NON_HERMETIC_VARIABLES = (
    "ENVIRONMENT",
    "LOG_LEVEL",
    "PORT",
    "GRAFANA_USER",
    "GRAFANA_PASSWORD",
    "INIS_LIVE_LLM",
    "INIS_TEST_USE_ENV",
)

#: Every group removed from the test environment, in report order.
HERMETIC_GROUPS: dict[str, tuple[str, ...]] = {
    "services": SERVICE_VARIABLES,
    "security": SECURITY_VARIABLES,
    "live": LIVE_VARIABLES,
    "configuration": CONFIGURATION_VARIABLES,
}

#: Every variable the policy knows about: a new one must be classified here.
CLASSIFIED_VARIABLES: frozenset[str] = frozenset(
    {name for names in HERMETIC_GROUPS.values() for name in names} | set(NON_HERMETIC_VARIABLES)
)

#: ``=1`` keeps the developer's whole ``.env`` (real-stack runs).
STACK_OPT_IN = "INIS_TEST_USE_ENV"

#: ``=1`` keeps ``LLM_API_KEY`` so a live provider call is really served.
LIVE_LLM_OPT_IN = "INIS_LIVE_LLM"

_TRUTHY = {"1", "true", "yes", "on"}


def _enabled(environ: MutableMapping[str, str], name: str) -> bool:
    """Return whether the opt-in flag *name* is set to a truthy value."""
    return environ.get(name, "").strip().lower() in _TRUTHY


def enforce_hermetic_environment(
    environ: MutableMapping[str, str],
) -> dict[str, list[str]]:
    """Remove the behaviour-changing variables from *environ*.

    Args:
        environ: Mapping to clean in place (``os.environ`` in ``conftest``).

    Returns:
        The removed names per group (``services``, ``security``, ``live``), so a
        test can assert the policy instead of trusting it.
    """
    removed: dict[str, list[str]] = {"services": [], "security": [], "live": [], "configuration": []}
    if _enabled(environ, STACK_OPT_IN):
        return removed
    for group, names in HERMETIC_GROUPS.items():
        if group == "live" and _enabled(environ, LIVE_LLM_OPT_IN):
            # The LLM key is opted in, the other providers stay out.
            names = tuple(name for name in names if name != "LLM_API_KEY")
        for name in names:
            if name in environ:
                del environ[name]
                removed[group].append(name)
    return removed


def load_environment(
    path: str | Path | None = None,
    *,
    environ: MutableMapping[str, str] | None = None,
) -> dict[str, str]:
    """Load ``.env`` (never in production) then apply the hermetic policy.

    Returns:
        The variables the file actually contributed, for reporting.
    """
    target = os.environ if environ is None else environ
    applied = bootstrap_environment(path, environ=target)
    enforce_hermetic_environment(target)
    return applied
