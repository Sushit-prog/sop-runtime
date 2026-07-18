"""Compiler error types."""

from __future__ import annotations


class LoweringError(Exception):
    """Raised when AST->IR lowering encounters an unexpected input shape.

    This should not be reachable if M2 validated the AST correctly —
    these are assertion-style defensive checks, not a new validation
    layer.
    """

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)
