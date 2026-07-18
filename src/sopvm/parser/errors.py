"""Error types for the SOP YAML parser.

Every diagnostic carries a human-readable message. Schema validation
errors also carry the JSON path to the offending field. Semantic errors
name the specific step id when applicable.
"""

from __future__ import annotations


class ParseError(Exception):
    """Base exception for all SOP parse errors.

    Attributes:
        message: Human-readable description of the error.
    """

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class SchemaValidationError(ParseError):
    """Raised when the YAML document fails JSON Schema validation.

    Attributes:
        path: JSON path into the document (list of keys/indices).
        cause: Raw jsonschema error message, if available.
    """

    def __init__(
        self,
        message: str,
        path: list[str | int] | None = None,
        cause: str | None = None,
    ) -> None:
        self.path = path or []
        self.cause = cause
        super().__init__(message)


class SemanticError(ParseError):
    """Raised when a semantic rule is violated.

    Attributes:
        step_id: The offending step id, if applicable.
    """

    def __init__(
        self, message: str, step_id: str | None = None
    ) -> None:
        self.step_id = step_id
        super().__init__(message)
