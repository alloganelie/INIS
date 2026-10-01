"""The artefacts client keeps its two promises (§24.2, C14, P10).

The plan's L1.6 items are about the frontend, and a browser build is not
available to this suite. Two of the promises, however, are visible in the source
and are exactly the ones that were broken:

* the ``Artifact`` type ``api/artifacts.ts`` imports from ``../types`` must
  really be exported — before L1.6 the module imported a type that did not exist;
* a network failure must not look like "no artifact": only a ``404`` (unknown
  request) may become an empty result, every other error has to propagate
  (§37 « signaler > inventer »). The removed ``catch { return [] }`` is the
  pitfall P10 this test makes impossible to reintroduce silently.

It is a source-level guard on purpose: it runs in the same ``pytest`` as the
backend, so a regression is caught by CI and not only by a manual build.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
FRONTEND_SRC = REPO_ROOT / "frontend" / "src"
CLIENT = FRONTEND_SRC / "api" / "artifacts.ts"
TYPES_INDEX = FRONTEND_SRC / "types" / "index.ts"
TYPES_API = FRONTEND_SRC / "types" / "api.ts"

pytestmark = pytest.mark.skipif(
    not CLIENT.exists(), reason="le frontend n'est pas présent dans cette copie"
)


def _read(path: Path) -> str:
    """Return the source of *path* (the frontend is UTF-8)."""
    return path.read_text(encoding="utf-8")


def _code_only(source: str) -> str:
    """Return *source* without its comments.

    The removed pattern is itself documented in a comment ("the previous
    ``catch { return [] }``…"): a source scan that read the comments would
    forbid writing the very explanation that prevents a regression.
    """
    without_blocks = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return "\n".join(
        line for line in without_blocks.splitlines() if not line.strip().startswith("//")
    )


class TestArtifactType:
    """The type the client imports exists and is reachable from ``../types``."""

    def test_the_type_is_exported(self) -> None:
        assert re.search(r"export interface Artifact\b", _read(TYPES_API))

    def test_the_barrel_re_exports_it(self) -> None:
        index = _read(TYPES_INDEX)
        assert "export * from './api'" in index or "Artifact" in index

    def test_the_client_imports_it_from_the_barrel(self) -> None:
        assert re.search(r"import\s*\{[^}]*Artifact[^}]*\}\s*from\s*'\.\./types'", _read(CLIENT))


class TestErrorsAreNotSwallowed:
    """Only a ``404`` may become an empty result; everything else propagates."""

    def test_no_silent_catch_remains(self) -> None:
        """A ``catch {`` without binding cannot inspect the error: it is banned."""
        assert not re.search(r"catch\s*\{", _code_only(_read(CLIENT)))

    def test_every_catch_inspects_the_status(self) -> None:
        """Each ``catch`` block mentions the 404 it treats separately."""
        blocks = re.split(r"catch\s*\(error", _code_only(_read(CLIENT)))[1:]
        assert blocks, "le client doit capturer les erreurs pour les distinguer"
        offenders = [block[:120] for block in blocks if "404" not in block]
        assert offenders == [], f"catch sans distinction du 404 : {offenders}"

    def test_every_catch_rethrows(self) -> None:
        """What is not a 404 is rethrown, never converted into a value."""
        source = _code_only(_read(CLIENT))
        assert source.count("catch (error") == source.count("throw error;")

    def test_the_empty_result_is_documented_as_a_404(self) -> None:
        """The comment states the rule, so the next reader does not relearn it."""
        source = _read(CLIENT)
        assert "404" in source and "propagates" in source


PANEL = FRONTEND_SRC / "components" / "ArtifactsPanel.tsx"
ERROR_MAP = FRONTEND_SRC / "api" / "artifactErrors.ts"
REQUEST_STATUS = FRONTEND_SRC / "pages" / "RequestStatus.tsx"


class TestTheArtefactsUIUsesTheExistingContracts:
    """§24.2/§18.1/§19.3 — la UI consomme l'API, elle ne la réinvente pas."""

    def test_the_client_exposes_the_history_and_the_download(self) -> None:
        source = _read(CLIENT)
        for function in ("listArtifactVersions", "getArtifactLineage", "downloadArtifact"):
            assert f"export async function {function}" in source, f"{function} manque"

    def test_the_client_uses_the_backend_routes(self) -> None:
        source = _read(CLIENT)
        for route in ("/artifacts/${id}/versions", "/artifacts/${id}/lineage", "/download"):
            assert route in source, f"la route {route} doit être appelée telle quelle"

    def test_the_types_of_the_new_contracts_exist(self) -> None:
        types = _read(TYPES_API)
        for name in (
            "ArtifactVersion",
            "ArtifactVersionList",
            "ArtifactLineage",
            "ArtifactLineageView",
            "ArtifactDeliveryEvent",
        ):
            assert re.search(rf"export interface {name}\b", types), f"{name} manque"

    def test_the_error_mapping_distinguishes_every_refusal(self) -> None:
        """403, 401, 404, 503, 5xx et l'absence de réponse sont distingués."""
        source = _code_only(_read(ERROR_MAP))
        for status in ("401", "403", "404", "503"):
            assert status in source, f"le statut {status} doit être décrit"
        assert ">= 500" in source, "les erreurs serveur doivent être nommées"
        assert "isAxiosError" in source and "status === undefined" in source, (
            "l'absence de réponse (réseau) doit être distinguée d'un statut HTTP"
        )
        assert "message" in source and "kind" in source

    def test_the_panel_never_swallows_an_error(self) -> None:
        """Aucun ``catch`` sans liaison, et chaque échec devient visible."""
        code = _code_only(_read(PANEL))
        assert not re.search(r"catch\s*\{", code), "aucun catch silencieux dans la UI"
        blocks = re.split(r"catch\s*\(", code)[1:]
        assert blocks, "la UI doit capturer les erreurs pour les montrer"
        offenders = [block[:80] for block in blocks if "setState" not in block]
        assert offenders == [], f"catch qui n'affiche rien : {offenders}"
        assert 'role="alert"' in _read(PANEL), "les erreurs doivent être annoncées"

    def test_the_panel_goes_through_the_api_module(self) -> None:
        """La UI n'appelle pas axios directement : le contrat reste dans `api/`."""
        source = _read(PANEL)
        assert "from '../api/artifacts'" in source
        assert "axios" not in _code_only(source)
        assert "describeArtifactError" in source

    def test_the_page_renders_the_panel(self) -> None:
        """La page d'état expose la section « Artefacts » (§31.1)."""
        source = _read(REQUEST_STATUS)
        assert "ArtifactsPanel" in source and "<ArtifactsPanel" in source
