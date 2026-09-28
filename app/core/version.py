"""Single source of truth for the API version (§41.15).

Before this module the version string was duplicated in ``app/main.py``,
``app/api/v1/system/changelog_router.py`` and
``app/api/v1/system/health_router.py`` — three places that could drift
independently. Every surface now imports :data:`API_VERSION` from here, and
``tests/unit/core/test_version_consistency.py`` asserts that ``pyproject.toml``
and ``docs/changelog.json`` agree with it.
"""

from __future__ import annotations

#: Released API version (semver). Keep in sync with ``pyproject.toml``.
API_VERSION = "2.0.0"

__all__ = ["API_VERSION"]
