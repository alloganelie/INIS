"""``§41.14`` backward-compatibility gate — command-line entry point.

Thin CLI over :class:`scripts.migrations.check_backward_compat.BackwardCompatChecker`
so CI and pre-commit hooks can call it without importing the test suite.

Usage::

    python scripts/check_backward_compat.py migrations/versions/

Exit code 0 when no ``error`` violation is found, 1 otherwise. Warnings
(``BC005``: ``CREATE INDEX`` without ``CONCURRENTLY``) are printed but do not
fail the build.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:  # allow `python scripts/check_backward_compat.py`
    sys.path.insert(0, str(ROOT))

from scripts.migrations.check_backward_compat import BackwardCompatChecker  # noqa: E402

DEFAULT_TARGET = "migrations/versions"


def main(argv: list[str] | None = None) -> int:
    """Check *argv[0]* (or ``migrations/versions``) and return the exit code."""
    args = list(sys.argv[1:] if argv is None else argv)
    target = Path(args[0]) if args else Path(DEFAULT_TARGET)
    if not target.exists():
        print(f"ERROR: path not found: {target}")
        return 1

    checker = BackwardCompatChecker()
    violations = (
        checker.check_directory(target) if target.is_dir() else checker.check_file(target)
    )
    errors = [v for v in violations if v.severity == "error"]
    warnings = [v for v in violations if v.severity == "warning"]

    for warning in warnings:
        print(f"WARN  [{warning.rule_id}] {warning.file}:{warning.line} - {warning.message}")
    for error in errors:
        print(f"ERROR [{error.rule_id}] {error.file}:{error.line} - {error.message}")

    if errors:
        print(f"FAIL: {len(errors)} breaking change(s) in {target}")
        return 1
    print(f"OK: 0 breaking change in {target} ({len(warnings)} warning(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
