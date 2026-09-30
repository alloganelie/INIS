"""The ``app.storage.repositories`` package exports what it promises (§27).

The plan asks for an "import test" on the repositories package: a repository
that is not exported cannot be reached by ``from app.storage.repositories import
ArtifactRepository``, and that is the failure mode this contract catches. It
also asserts that every exported name is the real class (and not, say, the Core
table of the same module) and that the package has no duplicate name.
"""

from __future__ import annotations

import importlib

import pytest

from app.storage import repositories

#: Every repository the application may import by package name.
EXPECTED_EXPORTS = (
    "AccountRepository",
    "ArtifactRepository",
    "ConflictRepository",
    "DatasetRepository",
    "DocumentRepository",
    "EmbeddingRepository",
    "EvidenceRepository",
    "InformationPackageRepository",
    "InformationUnitRepository",
    "InformationVersionRepository",
    "PlanRepository",
    "RequestRepository",
    "SessionRepository",
    "SourceRepository",
    "TransformationRepository",
)


def test_every_expected_repository_is_exported() -> None:
    """A missing export is a missing repository, not a naming detail."""
    missing = [name for name in EXPECTED_EXPORTS if not hasattr(repositories, name)]
    assert missing == [], f"repositories non exportés : {missing}"


def test_expected_exports_are_declared_in_dunder_all() -> None:
    """``__all__`` lists them, so ``import *`` and tooling see the same surface."""
    missing = [name for name in EXPECTED_EXPORTS if name not in repositories.__all__]
    assert missing == [], f"absents de __all__ : {missing}"


@pytest.mark.parametrize("name", EXPECTED_EXPORTS)
def test_export_is_a_repository_class(name: str) -> None:
    """Each export is a class of the package exposing at least one operation.

    Two shapes coexist on purpose: the Core-table repositories expose
    classmethods over an engine (``SourceRepository.get(engine, id)``) while the
    session-bound ones are instantiated with a session (``AccountRepository``).
    The shared contract is "a class of this package with an operation", which is
    what the callers actually rely on.
    """
    exported = getattr(repositories, name)
    assert isinstance(exported, type), f"{name} n'est pas une classe"
    assert exported.__module__.startswith("app.storage.repositories")
    operations = [
        attribute
        for attribute in dir(exported)
        if not attribute.startswith("_") and callable(getattr(exported, attribute))
    ]
    assert operations, f"{name} n'expose aucune opération"


def test_no_name_is_exported_twice() -> None:
    """``__all__`` has no duplicate: the surface is unambiguous."""
    assert len(repositories.__all__) == len(set(repositories.__all__))


def test_the_package_imports_cleanly_from_a_fresh_module_object() -> None:
    """A fresh import of the package succeeds (no circular import at import time)."""
    reloaded = importlib.reload(repositories)
    assert set(EXPECTED_EXPORTS) <= set(reloaded.__all__)
