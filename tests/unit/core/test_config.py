"""Vérification des fichiers de configuration TOML per §38 et §4.1.

Les fichiers `configs/*.toml` doivent :
1. Être des fichiers TOML valides et non vides.
2. Contenir les sections obligatoires canoniques.
3. Correspondre aux valeurs du runtime pour les seuils par défaut.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from app.connectors.files.upload_policy import DEFAULT_MAX_UPLOAD_BYTES
from app.domain.value_objects.request_constraints import (
    DEFAULT_CONSTRAINTS,
    DEFAULT_REQUIRED_OUTPUT,
)
from app.knowledge.normalization.limits import (
    DEFAULT_MAX_INFORMATION_UNITS_PER_REQUEST,
)
from app.planning.limits import (
    DEFAULT_MAX_PARALLEL_TOOL_CALLS,
    DEFAULT_MAX_PLAN_STEPS,
)

ROOT = Path(__file__).resolve().parents[3]
CONFIGS_DIR = ROOT / "configs"
CONFIG_PROFILES = ("default.toml", "development.toml", "test.toml", "production.toml")


@pytest.mark.parametrize("filename", CONFIG_PROFILES)
def test_config_file_exists_and_is_valid_toml(filename: str) -> None:
    path = CONFIGS_DIR / filename
    assert path.exists(), f"Configuration file {filename} does not exist"
    assert path.stat().st_size > 0, f"Configuration file {filename} is empty"

    data = tomllib.loads(path.read_text(encoding="utf-8"))
    assert "environment" in data
    assert "request_defaults" in data
    assert "limits" in data
    assert "cache" in data
    assert "llm" in data
    assert "web" in data


def test_default_config_matches_domain_constants() -> None:
    default_path = CONFIGS_DIR / "default.toml"
    data = tomllib.loads(default_path.read_text(encoding="utf-8"))

    req = data["request_defaults"]
    assert req["minimum_confidence"] == DEFAULT_CONSTRAINTS.minimum_confidence
    assert (
        req["maximum_execution_time_seconds"]
        == DEFAULT_CONSTRAINTS.maximum_execution_time_seconds
    )
    assert req["maximum_iterations"] == DEFAULT_CONSTRAINTS.maximum_iterations
    assert req["maximum_web_depth"] == DEFAULT_CONSTRAINTS.maximum_web_depth
    assert req["required_output_format"] == DEFAULT_REQUIRED_OUTPUT.format

    limits = data["limits"]
    assert limits["max_plan_steps"] == DEFAULT_MAX_PLAN_STEPS
    assert limits["max_parallel_tool_calls"] == DEFAULT_MAX_PARALLEL_TOOL_CALLS
    # §36.6 — the upload ceiling of the deployment mirrors the runtime default:
    # the two must never drift, otherwise a documented limit is not the one used.
    assert limits["max_upload_bytes"] == DEFAULT_MAX_UPLOAD_BYTES
    # ADR 007 — the chunking threshold is a deployment setting too, not a comment
    # buried in an ADR: the profile and the runtime read the same number.
    assert (
        limits["max_information_units_per_request"]
        == DEFAULT_MAX_INFORMATION_UNITS_PER_REQUEST
    )

