"""Contract between the code and ``.env.example`` (§4, §19).

The example file is the documented list of what a deployment must provide. A
variable read by ``app/`` and absent from that file is an undocumented
dependency: the reader has no way to know the feature exists until it silently
degrades. This test fails on that drift, in both directions:

* every variable read by ``app/`` must be documented;
* ``.env.example`` must never carry a real-looking secret, and ``.env`` itself
  must stay git-ignored so a local key never reaches a commit.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from tests.env_policy import CLASSIFIED_VARIABLES

REPO_ROOT = Path(__file__).resolve().parents[3]
APP_DIR = REPO_ROOT / "app"
EXAMPLE = REPO_ROOT / ".env.example"

#: How the application reads a variable (get, getenv, index, or a named constant).
_READ_PATTERNS = (
    re.compile(r"os\.environ\.get\(\s*[\"']([A-Z][A-Z0-9_]+)[\"']"),
    re.compile(r"os\.getenv\(\s*[\"']([A-Z][A-Z0-9_]+)[\"']"),
    re.compile(r"os\.environ\[\s*[\"']([A-Z][A-Z0-9_]+)[\"']\s*\]"),
    re.compile(r"_ENV_VAR\s*=\s*[\"']([A-Z][A-Z0-9_]+)[\"']"),
    re.compile(r"ENV_[A-Z_]*\s*=\s*[\"']([A-Z][A-Z0-9_]+)[\"']"),
)

#: Values that would mean a real credential was committed by mistake.
_SECRET_SHAPES = (re.compile(r"^(sk-|rk-|ghp_|AKIA)"), re.compile(r"^eyJ[A-Za-z0-9_-]{10,}"))


def _documented_names() -> set[str]:
    """Return the variable names declared in ``.env.example``."""
    names = set()
    for line in EXAMPLE.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        names.add(stripped.split("=", 1)[0].strip())
    return names


def _read_names() -> set[str]:
    """Return every environment variable name read by ``app/``."""
    names: set[str] = set()
    for path in sorted(APP_DIR.rglob("*.py")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in _READ_PATTERNS:
            names.update(pattern.findall(text))
    return names


def test_every_variable_read_by_app_is_documented() -> None:
    """No hidden dependency: read by the code implies documented in the example."""
    missing = sorted(_read_names() - _documented_names())
    assert missing == [], f"variables lues par app/ et absentes de .env.example : {missing}"


def test_example_carries_no_real_secret() -> None:
    """The example may hold dev placeholders, never a credential from a provider."""
    offenders = []
    for line in EXAMPLE.read_text(encoding="utf-8").splitlines():
        if "=" not in line or line.strip().startswith("#"):
            continue
        name, _, value = line.partition("=")
        value = value.strip()
        if value and any(shape.match(value) for shape in _SECRET_SHAPES):
            offenders.append(name.strip())
    assert offenders == [], f"valeurs ressemblant à un secret dans .env.example : {offenders}"


def test_env_is_git_ignored() -> None:
    """A local ``.env`` (real keys) can never be committed."""
    env_file = REPO_ROOT / ".env"
    try:
        result = subprocess.run(
            ["git", "check-ignore", "-q", str(env_file.name)],
            cwd=REPO_ROOT,
            capture_output=True,
            check=False,
        )
    except FileNotFoundError:  # pragma: no cover - git absent from the image
        pytest.skip("git n'est pas disponible dans cet environnement")
    assert result.returncode == 0, ".env doit rester ignoré par git (.gitignore)"


def test_every_documented_variable_is_classified_by_the_test_policy() -> None:
    """A new documented variable must be classified hermetic or not.

    ``tests/env_policy.py`` removes the variables that change behaviour so the
    suite stays deterministic whatever the machine's ``.env`` holds. That
    guarantee only holds if the policy knows every variable — this test is what
    forces the classification of the next one.
    """
    unclassified = sorted(_documented_names() - CLASSIFIED_VARIABLES)
    assert unclassified == [], (
        "variables documentées dans .env.example mais non classées dans "
        f"tests/env_policy.py : {unclassified}"
    )
