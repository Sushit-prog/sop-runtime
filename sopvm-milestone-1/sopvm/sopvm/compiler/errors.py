"""Compiler error types for the SOPVM parser.

Every diagnostic the parser can produce is represented as an
`SOPParseError` so the CLI (and any embedding application) can render
consistent, line-numbered messages instead of raw Python tracebacks.
SOPs are authored by process owners, not engineers, so the error
message *is* the product here as much as the parser logic is.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SOPParseError(Exception):
    """A single, user-facing parse error.

    Attributes:
        message: Human-readable description of what went wrong.
        line: 1-indexed source line the error is anchored to, or
            ``None`` if the error applies to the document as a whole
            (e.g. a completely missing frontmatter block).
        suggestion: Optional "did you mean" style hint, e.g. for a
            misspelled frontmatter key.
    """

    message: str
    line: int | None = None
    suggestion: str | None = None

    def __str__(self) -> str:
        location = f"line {self.line}: " if self.line is not None else ""
        base = f"{location}{self.message}"
        if self.suggestion:
            base += f" (did you mean: {self.suggestion}?)"
        return base


class SOPParseErrors(Exception):
    """A batch of one or more `SOPParseError`s raised together.

    The parser collects as many independent errors as it can safely
    find before raising, rather than stopping at the first problem,
    so `sopvm compile --check` can show a complete diagnostic report
    in a single pass instead of a fix-one-rerun-repeat loop.
    """

    def __init__(self, errors: list[SOPParseError]):
        if not errors:
            raise ValueError("SOPParseErrors requires at least one error")
        self.errors = errors
        super().__init__(f"{len(errors)} parse error(s)")

    def __str__(self) -> str:
        return "\n".join(str(e) for e in self.errors)
