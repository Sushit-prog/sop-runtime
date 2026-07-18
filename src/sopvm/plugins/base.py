"""Tool provider protocol and result types (Milestone 8).

Per INTERFACES.md §6:

    class ToolProvider(Protocol):
        def declared_capabilities(self) -> list[str]: ...
        def invoke(self, capability: CapabilityToken, args: dict) -> ToolResult: ...

- ``invoke`` is never called directly by step logic — only by the gate
  (M7), which checks ``capability`` against ``capabilities_paged`` for
  the current step first.
- A provider that lies about ``declared_capabilities()`` (requests more
  at invoke time than it declared) is caught by the sandbox (M8).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from sopvm.capability.token import CapabilityToken


@dataclass(frozen=True)
class ToolResult:
    """Result of a tool invocation.

    Attributes:
        success: Whether the tool call succeeded.
        data: Arbitrary return data from the tool.
        error: Human-readable error message, if any.
    """

    success: bool
    data: Any = field(default=None)
    error: str | None = None


@runtime_checkable
class ToolProvider(Protocol):
    """Protocol for tool providers (plugins).

    Each provider declares which capabilities it can handle, and
    implements the actual tool invocation.
    """

    def declared_capabilities(self) -> list[str]:
        """Return the list of capability strings this provider handles."""
        ...

    def invoke(self, capability: CapabilityToken, args: dict) -> ToolResult:
        """Invoke the tool with the given capability and arguments."""
        ...
