"""Guard tests for secret hygiene (B4-ter-5).

These assertions run in CI: the moment somebody versionn a real
``secrets.yaml`` or drops a live key in a tracked file, the suite goes red.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

# tests/unit/security/test_secret_hygiene.py -> repository root
ROOT = Path(__file__).resolve().parents[3]

#: Credential shapes that must never appear in a tracked file.
SECRET_PATTERNS: dict[str, str] = {
    "openai_key": r"sk-(?:or-v1|proj)-[A-Za-z0-9_-]{20,}",
    "stripe_key": r"sk_(?:live|test)_[A-Za-z0-9]{16,}",
    "google_key": r"AIza[0-9A-Za-z_-]{30,}",
    "github_token": r"gh[pousr]_[A-Za-z0-9]{20,}",
    "gitlab_token": r"glpat-[A-Za-z0-9_-]{16,}",
    "slack_token": r"xox[baprs]-[A-Za-z0-9-]{10,}",
    "aws_access_key": r"AKIA[0-9A-Z]{16}",
    "private_key": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
}


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout


def _tracked_files() -> list[Path]:
    return [ROOT / rel for rel in _git("ls-files").splitlines() if rel]


def test_only_example_secret_files_are_tracked() -> None:
    """No real secrets.yaml / .env is versioned; only the .example files."""
    offenders = [
        path.relative_to(ROOT).as_posix()
        for path in _tracked_files()
        if path.name in ("secrets.yaml", "secrets.yml", ".env", "credentials.json")
    ]
    assert offenders == [], f"versionn des fichiers de secrets : {offenders}"


def test_secrets_example_is_still_tracked() -> None:
    """The placeholder template must remain available to operators."""
    tracked = _git("ls-files").splitlines()
    assert "deploy/cloud/k8s/secrets.yaml.example" in tracked


@pytest.mark.parametrize("path", [".env", "foo.pem", "foo.key", "x.p12", "x.pfx"])
def test_gitignore_covers_sensitive_patterns(path: str) -> None:
    """.env, *.pem, *.key, *.p12 and *.pfx are ignored."""
    result = subprocess.run(
        ["git", "check-ignore", "-q", path], cwd=ROOT, capture_output=True
    )
    assert result.returncode == 0, f"{path} should be gitignored"


def test_gitignore_covers_deployment_secrets() -> None:
    """deploy/**/secrets.yaml is ignored (B4-ter-5)."""
    for path in (
        "deploy/k8s/secrets.yaml",
        "deploy/cloud/k8s/secrets.yaml",
        "deploy/prod/credentials.json",
    ):
        result = subprocess.run(
            ["git", "check-ignore", "-q", path], cwd=ROOT, capture_output=True
        )
        assert result.returncode == 0, f"{path} should be gitignored"


def test_example_secret_file_is_not_ignored() -> None:
    """The .example template must stay trackable."""
    result = subprocess.run(
        ["git", "check-ignore", "-q", "deploy/cloud/k8s/secrets.yaml.example"],
        cwd=ROOT,
        capture_output=True,
    )
    assert result.returncode != 0, "the .example template must remain trackable"


def test_no_live_credential_in_tracked_files() -> None:
    """No tracked file contains a credential-shaped token."""
    compiled = {name: re.compile(pattern) for name, pattern in SECRET_PATTERNS.items()}
    # Documentation placeholders are not secrets.
    allowed = {"deploy/cloud/README.md", ".env.example"}

    offenders: list[str] = []
    for path in _tracked_files():
        rel = path.relative_to(ROOT).as_posix()
        if rel in allowed or not path.is_file():
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for name, pattern in compiled.items():
            if pattern.search(content):
                offenders.append(f"{rel} ({name})")
    assert offenders == [], f"credentials detectees dans des fichiers versionnes : {offenders}"


def test_security_checklist_is_documented() -> None:
    """deploy/cloud/README.md carries the four mandatory production rules."""
    readme = (ROOT / "deploy" / "cloud" / "README.md").read_text(encoding="utf-8")
    assert "SECURITY CHECKLIST" in readme
    for rule in (
        "INIS_AUTH_ENABLED=true",
        "INIS_RATE_LIMIT_ENABLED=true",
        "JWT_SECRET",
        "secrets.yaml",
    ):
        assert rule in readme, f"checklist security incomplete : {rule}"
