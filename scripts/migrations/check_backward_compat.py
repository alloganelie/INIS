"""Backward compatibility checker for Alembic migrations per §41.14.

Refuses non-backward-compatible DDL:
- DROP COLUMN, ALTER COLUMN TYPE, DROP TABLE (ERROR)
- ADD COLUMN NOT NULL without server default (ERROR)
- CREATE INDEX without CONCURRENTLY (WARNING)
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import List


@dataclass
class Violation:
    severity: str  # "error" | "warning"
    rule_id: str
    message: str
    line: int
    file: str = ""


class BackwardCompatChecker:
    """AST-based Alembic migration checker enforcing §41.14 zero-downtime rules."""

    ERROR_DROP_COLUMN = "BC001"
    ERROR_ALTER_COLUMN_TYPE = "BC002"
    ERROR_DROP_TABLE = "BC003"
    ERROR_ADD_NOT_NULL_NO_DEFAULT = "BC004"
    WARN_CREATE_INDEX_NO_CONCURRENT = "BC005"

    def check_file(self, path: Path | str) -> List[Violation]:
        path = Path(path)
        content = path.read_text(encoding="utf-8")
        tree = ast.parse(content, filename=str(path))
        violations: List[Violation] = []

        # Find the upgrade() function definition
        upgrade_node = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "upgrade":
                upgrade_node = node
                break

        if upgrade_node is None:
            return violations

        for node in ast.walk(upgrade_node):
            if not isinstance(node, ast.Call):
                continue

            func_name = self._get_call_name(node.func)
            if not func_name:
                continue

            # 1. DROP COLUMN
            if func_name in ("op.drop_column", "drop_column"):
                violations.append(
                    Violation(
                        severity="error",
                        rule_id=self.ERROR_DROP_COLUMN,
                        message="DROP COLUMN breaks zero-downtime blue/green deployment (§41.14)",
                        line=node.lineno,
                        file=str(path),
                    )
                )

            # 2. DROP TABLE
            elif func_name in ("op.drop_table", "drop_table"):
                violations.append(
                    Violation(
                        severity="error",
                        rule_id=self.ERROR_DROP_TABLE,
                        message="DROP TABLE is forbidden in non-destructive rolling migrations (§41.14)",
                        line=node.lineno,
                        file=str(path),
                    )
                )

            # 3. ALTER COLUMN TYPE
            elif func_name in ("op.alter_column", "alter_column"):
                # Check if type_ argument is passed
                has_type = any(kw.arg == "type_" for kw in node.keywords)
                if has_type:
                    violations.append(
                        Violation(
                            severity="error",
                            rule_id=self.ERROR_ALTER_COLUMN_TYPE,
                            message="ALTER COLUMN type_ requires expand/contract migration pattern (§41.14)",
                            line=node.lineno,
                            file=str(path),
                        )
                    )

            # 4. ADD COLUMN NOT NULL without DEFAULT
            elif func_name in ("op.add_column", "add_column"):
                if self._is_add_not_null_no_default(node):
                    violations.append(
                        Violation(
                            severity="error",
                            rule_id=self.ERROR_ADD_NOT_NULL_NO_DEFAULT,
                            message="ADD COLUMN with nullable=False requires server_default for existing rows (§41.14)",
                            line=node.lineno,
                            file=str(path),
                        )
                    )

            # 5. CREATE INDEX without CONCURRENTLY (warning)
            elif func_name in ("op.create_index", "create_index"):
                has_concurrently = False
                for kw in node.keywords:
                    if kw.arg == "postgresql_concurrently":
                        if isinstance(kw.value, ast.Constant) and bool(kw.value.value):
                            has_concurrently = True
                if not has_concurrently:
                    violations.append(
                        Violation(
                            severity="warning",
                            rule_id=self.WARN_CREATE_INDEX_NO_CONCURRENT,
                            message="CREATE INDEX without postgresql_concurrently=True may lock writes (§41.14)",
                            line=node.lineno,
                            file=str(path),
                        )
                    )

        return violations

    def check_directory(self, dir_path: Path | str) -> List[Violation]:
        dir_path = Path(dir_path)
        violations: List[Violation] = []
        for file in sorted(dir_path.glob("*.py")):
            if file.name.startswith("__"):
                continue
            violations.extend(self.check_file(file))
        return violations

    @staticmethod
    def _get_call_name(node: ast.AST) -> str:
        if isinstance(node, ast.Attribute):
            val = getattr(node.value, "id", "")
            return f"{val}.{node.attr}" if val else node.attr
        if isinstance(node, ast.Name):
            return node.id
        return ""

    @staticmethod
    def _is_add_not_null_no_default(call_node: ast.Call) -> bool:
        # Check sa.Column arguments inside op.add_column("table", sa.Column(...))
        for arg in call_node.args:
            if isinstance(arg, ast.Call):
                cname = BackwardCompatChecker._get_call_name(arg.func)
                if "Column" in cname:
                    nullable_false = False
                    has_default = False
                    for kw in arg.keywords:
                        if kw.arg == "nullable":
                            if isinstance(kw.value, ast.Constant) and kw.value.value is False:
                                nullable_false = True
                        if kw.arg in ("server_default", "default"):
                            has_default = True
                    if nullable_false and not has_default:
                        return True
        return False


if __name__ == "__main__":
    import sys
    checker = BackwardCompatChecker()
    target_dir = Path("migrations/versions")
    if len(sys.argv) > 1:
        target_dir = Path(sys.argv[1])
    violations = checker.check_directory(target_dir)
    errors = [v for v in violations if v.severity == "error"]
    warnings = [v for v in violations if v.severity == "warning"]
    for w in warnings:
        print(f"WARN  [{w.rule_id}] {w.file}:{w.line} - {w.message}")
    for e in errors:
        print(f"ERROR [{e.rule_id}] {e.file}:{e.line} - {e.message}")
    if errors:
        sys.exit(1)
    print(f"OK: 0 errors across {target_dir}")
