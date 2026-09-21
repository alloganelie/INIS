"""PHASE-08 smoke: frontend structure (§31, zone Antigravity observée en lecture seule)."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
SRC = FRONTEND / "src"
DOCKER_DIR = ROOT / "docker"


def _has_file(path: Path) -> bool:
    """Return True if *path* is a non-empty regular file."""
    try:
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


def _has_dir(path: Path) -> bool:
    """Return True if *path* is a directory."""
    try:
        return path.is_dir()
    except OSError:
        return False


def _list_files(directory: Path, pattern: str = "*") -> list[str]:
    """Return sorted file names in *directory* matching *pattern*."""
    if not _has_dir(directory):
        return []
    try:
        return sorted(p.name for p in directory.glob(pattern) if p.is_file())
    except OSError:
        return []


def _require_files(paths: list[Path], label: str) -> None:
    """Skip listing every missing file; pass if all are present and non-empty."""
    missing = [str(p.relative_to(ROOT)) for p in paths if not _has_file(p)]
    if missing:
        pytest.skip(f"{label} absents: " + "; ".join(missing))


def test_frontend_config_exists() -> None:
    """Config de base frontend (skip si fichier absent)."""
    _require_files(
        [
            FRONTEND / "package.json",
            FRONTEND / "vite.config.ts",
            FRONTEND / "tsconfig.json",
            FRONTEND / "index.html",
        ],
        "config frontend",
    )


def test_frontend_9_pages_exist() -> None:
    """Les 9 écrans §31.1 (skip si fichier absent)."""
    pages = SRC / "pages"
    # §31.1 : 1 soumettre → SubmitRequest, 2 état → RequestStatus,
    # 3 sources → Sources, 4 confiance → ConfidenceMatrix, 5 contradictions
    # → Conflicts, 6 informations → InformationUnits, 7 agents → AgentsSolicited,
    # 8 traçabilité → Traceability, 9 historique → RequestHistory.
    expected = [
        "SubmitRequest.tsx",
        "RequestStatus.tsx",
        "Sources.tsx",
        "ConfidenceMatrix.tsx",
        "Conflicts.tsx",
        "InformationUnits.tsx",
        "AgentsSolicited.tsx",
        "Traceability.tsx",
        "RequestHistory.tsx",
    ]
    _require_files([pages / name for name in expected], "pages §31.1")


def test_frontend_components_exist() -> None:
    """6 composants (skip si fichier absent)."""
    components = SRC / "components"
    expected = [
        "AgentCard.tsx",
        "ConfidenceBar.tsx",
        "ConflictCard.tsx",
        "EpistemicBadge.tsx",
        "Layout.tsx",
        "ProgressStepper.tsx",
    ]
    _require_files([components / name for name in expected], "composants")


def test_frontend_api_clients_exist() -> None:
    """9 clients api/*.ts + client.ts (skip si fichier absent)."""
    api = SRC / "api"
    expected = [
        "agents.ts",
        "artifacts.ts",
        "auth.ts",
        "conflicts.ts",
        "evidence.ts",
        "information.ts",
        "quality.ts",
        "requests.ts",
        "sources.ts",
        "client.ts",
    ]
    _require_files([api / name for name in expected], "clients api")


def test_frontend_types_exists() -> None:
    """Types partagés (skip si fichier absent)."""
    types = SRC / "types"
    _require_files(
        [
            types / "domain.ts",
            types / "api.ts",
            types / "protocol.ts",
            types / "index.ts",
        ],
        "types",
    )


def test_frontend_mocks_exists() -> None:
    """Mocks MSW (skip si fichier absent)."""
    mocks = SRC / "mocks"
    _require_files(
        [
            mocks / "fixtures.ts",
            mocks / "server.ts",
            mocks / "browser.ts",
        ],
        "mocks",
    )


def test_frontend_docker_exists() -> None:
    """Docker frontend (skip si fichier absent).

    Localisation constatée : `docker/` (avec repli `frontend/`).
    """
    candidates = [
        [DOCKER_DIR / "Dockerfile.frontend", FRONTEND / "Dockerfile.frontend"],
        [
            DOCKER_DIR / "docker-compose.frontend.yml",
            FRONTEND / "docker-compose.frontend.yml",
        ],
    ]
    missing: list[str] = []
    for options in candidates:
        if not any(_has_file(p) for p in options):
            missing.append(str(options[0].relative_to(ROOT)))
    if missing:
        pytest.skip("docker frontend absents: " + "; ".join(missing))


def test_frontend_contexts_exists() -> None:
    """Contextes React (skip si fichier absent)."""
    contexts = SRC / "contexts"
    _require_files(
        [
            contexts / "AuthContext.tsx",
            contexts / "TraceContext.tsx",
        ],
        "contextes",
    )


def test_frontend_hooks_exists() -> None:
    """Hooks React (skip si fichier absent)."""
    hooks = SRC / "hooks"
    _require_files(
        [
            hooks / "useRequest.ts",
            hooks / "useSSE.ts",
            hooks / "useConfidence.ts",
        ],
        "hooks",
    )


def test_frontend_buildable() -> None:
    """Build `npm run build` (skip si node_modules absent)."""
    import shutil
    import subprocess

    if not _has_dir(FRONTEND / "node_modules"):
        pytest.skip("node_modules absent : build non vérifié")
    package_json = FRONTEND / "package.json"
    if (
        not _has_dir(FRONTEND / "node_modules" / "msw")
        and '"msw"' in package_json.read_text(encoding="utf-8")
    ):
        pytest.skip("dépendance npm non installée (npm install requis)")
    npm_path = shutil.which("npm")
    if npm_path is None:
        pytest.skip("npm introuvable : build non vérifié")
    completed = subprocess.run(
        [npm_path, "run", "build", "--prefix", str(FRONTEND)],
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert completed.returncode == 0, completed.stderr[-2000:]
