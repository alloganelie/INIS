"""Bootstrap of the optional ``.env`` file for development and tests (§4, §19).

Every deployment is expected to inject real environment variables (docker
compose, systemd, a secret manager). For local development the repository ships
``.env.example``; copying it to ``.env`` is the documented workflow, and
``.env`` is git-ignored (``.gitignore``) so a real key never reaches a commit.

This module is the single reader of that file, with three hard rules:

* **never in production** — when ``ENVIRONMENT``/``INIS_ENVIRONMENT`` names
  production, the file is not even opened: production secrets come from the
  platform, not from a file that a working copy could carry;
* **the process environment always wins** — a variable already present is never
  overwritten, so an operator or a test can always override the file;
* **no value is ever logged** — only the number of keys applied, because a
  secret in a log line is a leaked secret (§19).

Nothing here imports the application: :func:`bootstrap_environment` is called
from ``app/__init__.py`` (development convenience) and from ``tests/conftest.py``
(hermetic by default, see that module's policy).
"""

from __future__ import annotations

import logging
import os
import re
from collections.abc import MutableMapping
from pathlib import Path

__all__ = [
    "DEFAULT_ENV_FILE",
    "PRODUCTION_ENVIRONMENTS",
    "bootstrap_environment",
    "is_production",
    "load_env_file",
    "parse_env_file",
    "reset_bootstrap_cache",
]

logger = logging.getLogger(__name__)

#: Path of the file read when a caller does not name one.
DEFAULT_ENV_FILE = Path(".env")

#: Values of ``ENVIRONMENT``/``INIS_ENVIRONMENT`` that forbid reading a file.
PRODUCTION_ENVIRONMENTS = frozenset({"production", "prod"})

#: Environment variables used to detect the running environment.
_ENVIRONMENT_KEYS = ("INIS_ENVIRONMENT", "ENVIRONMENT")

_ASSIGNMENT = re.compile(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$")
_DOUBLE_QUOTE_ESCAPES = {"\\n": "\n", "\\t": "\t", '\\"': '"', "\\\\": "\\"}

_bootstrap_done = False


def is_production(environ: MutableMapping[str, str] | None = None) -> bool:
    """Return whether *environ* names a production environment.

    Args:
        environ: Mapping to inspect; defaults to ``os.environ``.
    """
    source = os.environ if environ is None else environ
    for key in _ENVIRONMENT_KEYS:
        if source.get(key, "").strip().lower() in PRODUCTION_ENVIRONMENTS:
            return True
    return False


def _unquote(raw: str) -> str:
    """Return *raw* unquoted, expanding the escapes accepted in ``.env`` files."""
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        inner = value[1:-1]
        if value[0] == '"':
            for escaped, replacement in _DOUBLE_QUOTE_ESCAPES.items():
                inner = inner.replace(escaped, replacement)
        return inner
    return value


def parse_env_file(text: str) -> dict[str, str]:
    """Parse the ``KEY=VALUE`` content of a ``.env`` file.

    Blank lines and lines whose first non-blank character is ``#`` are ignored,
    an optional ``export`` prefix is accepted, surrounding quotes are removed.
    A ``#`` inside a value is kept: only a leading ``#`` starts a comment, so a
    secret containing ``#`` is not silently truncated.
    """
    values: dict[str, str] = {}
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = _ASSIGNMENT.match(line.strip())
        if match is None:
            continue
        values[match.group(1)] = _unquote(match.group(2))
    return values


def load_env_file(
    path: str | Path | None = None,
    *,
    environ: MutableMapping[str, str] | None = None,
    override: bool = False,
) -> dict[str, str]:
    """Apply the values of *path* to *environ* and return what was applied.

    Args:
        path: File to read; defaults to :data:`DEFAULT_ENV_FILE`.
        environ: Target mapping; defaults to ``os.environ``.
        override: When ``True`` a file value replaces an existing one. Default
            ``False``: the process environment stays authoritative.

    Returns:
        The mapping actually applied (empty when the file is absent, when
        running in production, or when every key was already defined).

    Raises:
        Nothing: an unreadable file is a normal, documented configuration (the
        degraded modes are reported by ``GET /v1/health``), never a crash.
    """
    source = os.environ if environ is None else environ
    if is_production(source):
        return {}
    target = Path(path) if path is not None else DEFAULT_ENV_FILE
    try:
        text = target.read_text(encoding="utf-8")
    except OSError:
        return {}
    applied: dict[str, str] = {}
    for key, value in parse_env_file(text).items():
        if key in source and not override:
            continue
        source[key] = value
        applied[key] = value
    return applied


def bootstrap_environment(
    path: str | Path | None = None,
    *,
    environ: MutableMapping[str, str] | None = None,
    force: bool = False,
) -> dict[str, str]:
    """Load the development ``.env`` once per process; return the keys applied.

    Idempotent: the second call is a no-op unless *force* is set, so importing
    ``app`` from several entry points (API, Alembic, scripts, tests) never
    reapplies a stale file over values a caller set on purpose.
    """
    global _bootstrap_done
    if _bootstrap_done and not force:
        return {}
    applied = load_env_file(path, environ=environ)
    _bootstrap_done = True
    if applied:
        logger.info("environment: %d variable(s) loaded from .env", len(applied))
    return applied


def reset_bootstrap_cache() -> None:
    """Forget that the bootstrap ran (tests only)."""
    global _bootstrap_done
    _bootstrap_done = False
