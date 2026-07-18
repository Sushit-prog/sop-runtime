"""Public Python API surface for SOPVM.

Milestone 1 exposes exactly one entry point: `compile_check`, which
parses and validates a SOP source file without emitting an executable
artifact. IR lowering and `.sopc` codegen (a future `compile()`
returning a `CompiledProgram`) land in Milestone 2 — see
docs/architecture.md section 10 for the full milestone roadmap.
"""

from __future__ import annotations

from pathlib import Path

from .compiler.ast import Procedure
from .compiler.parser import parse

__all__ = ["compile_check"]


def compile_check(source_path: str | Path) -> Procedure:
    """Parse and validate a SOP source file.

    This is the library-level equivalent of `sopvm compile --check`.

    Args:
        source_path: Path to a SOP Markdown source file.

    Returns:
        The validated `Procedure` AST.

    Raises:
        SOPParseErrors: If the SOP fails to parse or validate.
        FileNotFoundError: If `source_path` does not exist.
    """
    path = Path(source_path)
    text = path.read_text(encoding="utf-8")
    return parse(text, source_path=str(path))
