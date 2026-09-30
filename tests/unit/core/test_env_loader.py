"""Tests of the ``.env`` bootstrap (§19: never a secret in production).

They assert the three rules of :mod:`app.core.env`: the file is parsed
predictably, the process environment always wins, and production never reads a
file. No test touches the real ``.env`` of the developer: every call gets an
explicit ``environ`` mapping and a temporary file.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.env import (
    bootstrap_environment,
    is_production,
    load_env_file,
    parse_env_file,
    reset_bootstrap_cache,
)


@pytest.fixture
def target() -> dict[str, str]:
    """A fake process environment, isolated per test."""
    return {}


@pytest.fixture(autouse=True)
def _reset_cache():
    """Forget the once-per-process bootstrap between tests."""
    reset_bootstrap_cache()
    yield
    reset_bootstrap_cache()


def _write(tmp_path: Path, content: str) -> Path:
    path = tmp_path / ".env"
    path.write_text(content, encoding="utf-8")
    return path


class TestParsing:
    """The parser accepts the usual ``.env`` shapes and nothing more."""

    def test_comments_export_and_quotes(self) -> None:
        text = (
            "# commentaire\n"
            "\n"
            "PLAIN=value\n"
            "export EXPORTED=exported-value\n"
            'DOUBLE="double value"\n'
            "SINGLE='single value'\n"
            "EMPTY=\n"
        )
        assert parse_env_file(text) == {
            "PLAIN": "value",
            "EXPORTED": "exported-value",
            "DOUBLE": "double value",
            "SINGLE": "single value",
            "EMPTY": "",
        }

    def test_hash_inside_a_value_is_kept(self) -> None:
        """A key containing ``#`` must not be truncated."""
        parsed = parse_env_file("LLM_API_KEY=sk-live#fragment\n")
        assert parsed == {"LLM_API_KEY": "sk-live#fragment"}

    def test_escapes_expand_only_in_double_quotes(self) -> None:
        parsed = parse_env_file('A="line\\nbreak"\nB=\'line\\nbreak\'\n')
        assert parsed == {"A": "line\nbreak", "B": "line\\nbreak"}

    def test_invalid_lines_are_ignored(self) -> None:
        assert parse_env_file("not an assignment\n=noname\n") == {}


class TestLoading:
    """``load_env_file`` applies what the file adds and nothing else."""

    def test_file_values_are_applied(self, tmp_path: Path, target: dict[str, str]) -> None:
        path = _write(tmp_path, "SERPER_API_KEY=from-file\nLLM_BASE_URL=\n")
        applied = load_env_file(path, environ=target)
        assert applied == {"SERPER_API_KEY": "from-file", "LLM_BASE_URL": ""}
        assert target["SERPER_API_KEY"] == "from-file"

    def test_process_environment_wins_by_default(
        self, tmp_path: Path, target: dict[str, str]
    ) -> None:
        target["SERPER_API_KEY"] = "from-shell"
        path = _write(tmp_path, "SERPER_API_KEY=from-file\n")
        assert load_env_file(path, environ=target) == {}
        assert target["SERPER_API_KEY"] == "from-shell"

    def test_override_replaces_the_process_value(
        self, tmp_path: Path, target: dict[str, str]
    ) -> None:
        target["SERPER_API_KEY"] = "from-shell"
        path = _write(tmp_path, "SERPER_API_KEY=from-file\n")
        load_env_file(path, environ=target, override=True)
        assert target["SERPER_API_KEY"] == "from-file"

    def test_missing_file_is_not_an_error(self, tmp_path: Path, target: dict[str, str]) -> None:
        assert load_env_file(tmp_path / "absent", environ=target) == {}


class TestProductionGuard:
    """Production never reads a file: the platform injects the secrets."""

    @pytest.mark.parametrize("value", ["production", "PRODUCTION", "prod"])
    def test_production_is_detected(self, value: str) -> None:
        assert is_production({"ENVIRONMENT": value}) is True

    def test_development_is_not_production(self) -> None:
        assert is_production({"ENVIRONMENT": "development"}) is False
        assert is_production({}) is False

    def test_environment_aliases_are_both_read(self) -> None:
        assert is_production({"INIS_ENVIRONMENT": "production"}) is True

    def test_file_is_not_read_in_production(
        self, tmp_path: Path, target: dict[str, str]
    ) -> None:
        target["ENVIRONMENT"] = "production"
        path = _write(tmp_path, "LLM_API_KEY=leaked\n")
        assert load_env_file(path, environ=target) == {}
        assert "LLM_API_KEY" not in target

    def test_bootstrap_is_idempotent(self, tmp_path: Path, target: dict[str, str]) -> None:
        path = _write(tmp_path, "SERPER_API_KEY=first\n")
        assert bootstrap_environment(path, environ=target) == {"SERPER_API_KEY": "first"}
        assert bootstrap_environment(path, environ=target) == {}
        assert target["SERPER_API_KEY"] == "first"

    def test_bootstrap_force_reapplies(self, tmp_path: Path, target: dict[str, str]) -> None:
        path = _write(tmp_path, "SERPER_API_KEY=first\n")
        bootstrap_environment(path, environ=target)
        target["SERPER_API_KEY"] = "changed"
        applied = bootstrap_environment(path, environ=target, force=True)
        # ``override`` stays False: force only re-arms the reader.
        assert applied == {}
        assert target["SERPER_API_KEY"] == "changed"
