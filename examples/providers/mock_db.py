"""Mock database provider (reference implementation, NOT production).

Illustrative provider for the ``db`` namespace. Handles read operations
on declared resources. Clearly commented as a non-production example.
"""

from __future__ import annotations

from sopvm.capability.token import CapabilityToken
from sopvm.plugins.base import ToolResult


class MockDbProvider:
    """Minimal mock database provider for testing and docs."""

    def __init__(self, data: dict[str, list[dict]] | None = None) -> None:
        self._data = data or {}

    def declared_capabilities(self) -> list[str]:
        """Only declares read capabilities on known resources."""
        caps = []
        for resource in self._data:
            caps.append(f"db:read({resource})")
        return caps

    def invoke(self, capability: CapabilityToken, args: dict) -> ToolResult:
        """Simulate a database read."""
        resource = capability.params
        # Extract resource name from bare param
        for key in resource:
            if resource[key] is True:
                rows = self._data.get(key, [])
                return ToolResult(success=True, data=rows)
        return ToolResult(success=False, error=f"unknown resource: {capability.raw}")
