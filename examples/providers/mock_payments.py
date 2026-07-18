"""Mock payments provider (reference implementation, NOT production).

Illustrative provider for the ``payments`` namespace. Handles refund
operations with ceiling enforcement. Clearly commented as a non-production
example.
"""

from __future__ import annotations

from sopvm.capability.token import CapabilityToken
from sopvm.plugins.base import ToolResult


class MockPaymentsProvider:
    """Minimal mock payments provider for testing and docs."""

    def declared_capabilities(self) -> list[str]:
        return ["payments:refund(max_amount<=1000.00)"]

    def invoke(self, capability: CapabilityToken, args: dict) -> ToolResult:
        """Simulate a refund operation."""
        return ToolResult(
            success=True,
            data={"refund_id": "mock-refund-001", "amount": args.get("amount", 0)},
        )
