"""Plugin package (Milestone 8)."""

from .base import ToolProvider, ToolResult
from .registry import ProviderRegistry
from .sandbox import ProviderIntegrityViolation, wrap_provider

__all__ = [
    "ProviderIntegrityViolation",
    "ProviderRegistry",
    "ToolProvider",
    "ToolResult",
    "wrap_provider",
]
