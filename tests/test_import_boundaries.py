"""Import boundary tests.

Enforces that no module outside ``src/sopvm/integrations/langgraph/``
imports ``langgraph``. This is an AST-based check, not a string grep,
to avoid false positives in comments/strings.

The rule: langgraph is an optional dependency. Core modules
(compiler/runtime/checker/capability/parser/ir/plugins) must work with
zero langgraph installed.
"""

import ast
from pathlib import Path

import pytest

SRC_ROOT = Path(__file__).resolve().parents[1] / "src" / "sopvm"
LANGGRAPH_ALLOWLIST = SRC_ROOT / "integrations" / "langgraph"


def _get_python_files() -> list[Path]:
    """Collect all .py files under src/sopvm/."""
    return list(SRC_ROOT.rglob("*.py"))


def _has_langgraph_import(filepath: Path) -> list[str]:
    """Parse a Python file's AST and return any langgraph import lines.

    Returns a list of strings describing the import (e.g. "import langgraph"
    or "from langgraph.graph import StateGraph").
    """
    try:
        tree = ast.parse(filepath.read_text(encoding="utf-8"), filename=str(filepath))
    except SyntaxError:
        return []

    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("langgraph"):
                    imports.append(f"import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.startswith("langgraph"):
                imports.append(f"from {node.module} import ...")
    return imports


class TestImportBoundary:
    def test_no_langgraph_imports_outside_allowlist(self):
        """No module outside integrations/langgraph/ imports langgraph."""
        violations = []
        for filepath in _get_python_files():
            # Skip the allowlist directory
            try:
                filepath.relative_to(LANGGRAPH_ALLOWLIST)
                continue  # This file is allowed to import langgraph
            except ValueError:
                pass  # Not in allowlist — check it

            imports = _has_langgraph_import(filepath)
            if imports:
                rel = filepath.relative_to(SRC_ROOT)
                violations.append(f"{rel}: {', '.join(imports)}")

        assert not violations, (
            "langgraph imported outside integrations/langgraph/:\n"
            + "\n".join(violations)
        )

    def test_allowlist_files_can_import_langgraph(self):
        """Files in integrations/langgraph/ are allowed to import langgraph."""
        # This test just verifies the allowlist path is correct
        assert LANGGRAPH_ALLOWLIST.exists()
        assert LANGGRAPH_ALLOWLIST.is_dir()
