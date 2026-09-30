"""Every checked box of the conformance plan cites proofs that exist (§33).

``docs/SPEC_CONFORMANCE_PLAN.md`` states its own rule: *no* ``[x]`` without a real
test name that proves it. This test enforces it mechanically, because the drift
is silent otherwise: during the L0–L6 lots, 20 citations pointed at test files
that had never been created (the proofs had been consolidated under other names),
and the boxes looked proven to anyone reading the plan.

What it checks, for every ``- [x]`` item:

* at least one ``tests/...py`` path is cited (a checked box without a proof is
  not checked, it is a claim);
* every cited file exists;
* every cited node (``file::Class`` / ``file::Class::test``) is really declared
  in that file.

A file mentioned **without** the ``tests/`` prefix is a correction note ("the
plan cited ``test_x.py``, which does not exist"), not a citation: that is how the
plan records a wrong citation without tripping this guard.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PLAN = REPO_ROOT / "docs" / "SPEC_CONFORMANCE_PLAN.md"

#: ``- [x] …`` / ``- [ ] …`` / ``- [~] …`` and the text that follows it.
_BOX = re.compile(r"^\s*- \[([x~ ])\]\s*(.*)$")
#: A citation: the ``tests/`` prefix is what separates a proof from a note.
_CITED_FILE = re.compile(r"tests[/\\][\w./\\-]+?\.py")
_CITED_NODE = re.compile(
    r"(tests[/\\][\w./\\-]+?\.py)::([A-Za-z_][\w]*)(?:::([A-Za-z_][\w]*))?"
)


def _boxes() -> list[tuple[str, int, str]]:
    """Return ``(state, line number, text)`` for every box, continuations included."""
    collected: list[list] = []
    current: list | None = None
    for number, line in enumerate(PLAN.read_text(encoding="utf-8").splitlines(), start=1):
        match = _BOX.match(line)
        if match:
            current = [match.group(1), number, [match.group(2)]]
            collected.append(current)
            continue
        if current is not None and line.strip() and not line.strip().startswith("#"):
            current[2].append(line)
    return [(state, number, "\n".join(parts)) for state, number, parts in collected]


def _checked_boxes() -> list[tuple[int, str]]:
    """Return the checked boxes with their full text."""
    return [(number, text) for state, number, text in _boxes() if state == "x"]


def test_the_plan_has_checked_boxes_to_audit() -> None:
    """The parse itself must work: an empty list would make every check vacuous."""
    assert len(_checked_boxes()) > 40


def test_every_checked_box_cites_a_proof() -> None:
    """A checked box without a cited test file is a claim, not a proof."""
    without_proof = [
        f"l.{number}"
        for number, text in _checked_boxes()
        if not _CITED_FILE.search(text)
    ]
    assert without_proof == [], f"cases cochées sans preuve citée : {without_proof}"


def test_every_cited_test_file_exists() -> None:
    """No citation may point at a file that was never created."""
    missing: list[str] = []
    for number, text in _checked_boxes():
        for match in _CITED_FILE.findall(text):
            path = match.replace("\\", "/")
            if not (REPO_ROOT / path).exists():
                missing.append(f"l.{number} -> {path}")
    assert missing == [], f"preuves citées absentes : {missing}"


def test_every_cited_node_is_declared() -> None:
    """A cited class or test name must exist in the file it points at."""
    missing: list[str] = []
    for number, text in _checked_boxes():
        for raw_path, first, second in _CITED_NODE.findall(text):
            path = REPO_ROOT / raw_path.replace("\\", "/")
            if not path.exists():
                continue
            content = path.read_text(encoding="utf-8", errors="ignore")
            for name in (first, second):
                if name and not re.search(rf"\b(?:def|class)\s+{re.escape(name)}\b", content):
                    missing.append(f"l.{number} -> {raw_path}::{name}")
    assert missing == [], f"nœuds cités absents : {missing}"
