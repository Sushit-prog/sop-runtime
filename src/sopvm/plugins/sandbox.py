"""Provider sandbox wrapper (Milestone 8).

Catches a provider lying about its own scope — invoking a capability
it didn't declare at registration time. This is a DIFFERENT threat
model than the SOP-level capability gate in M7 (that one trusts
providers; this one doesn't). Both checks are always applied together.
"""

from __future__ import annotations

from sopvm.capability.token import CapabilityToken, parse_capability

from .base import ToolProvider, ToolResult


class ProviderIntegrityViolation(Exception):
    """Raised when a provider attempts to invoke a capability it didn't declare.

    This is a defense-in-depth check: even if the M7 gate has a bug,
    the sandbox catches a lying provider.
    """

    def __init__(self, message: str, provider: ToolProvider,
                 capability: CapabilityToken) -> None:
        self.provider = provider
        self.capability = capability
        super().__init__(message)


class _SandboxWrapper:
    """Wraps a provider and checks invoke() calls against declared scope."""

    def __init__(self, provider: ToolProvider) -> None:
        self._provider = provider
        self._declared: set[tuple[str, str]] = set()
        for cap_str in provider.declared_capabilities():
            token = parse_capability(cap_str)
            self._declared.add((token.namespace, token.action))

    def declared_capabilities(self) -> list[str]:
        return self._provider.declared_capabilities()

    def invoke(self, capability: CapabilityToken, args: dict) -> ToolResult:
        key = (capability.namespace, capability.action)
        if key not in self._declared:
            raise ProviderIntegrityViolation(
                f"provider {type(self._provider).__name__!r} attempted to "
                f"invoke {capability.raw!r} which it did not declare",
                provider=self._provider,
                capability=capability,
            )
        return self._provider.invoke(capability, args)


def wrap_provider(provider: ToolProvider) -> ToolProvider:
    """Wrap a provider with sandbox integrity checks.

    Returns a new provider that checks, on every ``invoke()`` call,
    whether the requested capability is within what the provider
    declared at registration time. Raises ``ProviderIntegrityViolation``
    if not.
    """
    return _SandboxWrapper(provider)
