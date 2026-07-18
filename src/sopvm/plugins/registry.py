"""Provider registry (Milestone 8).

Matches incoming capability requests to registered providers by
namespace/action against each provider's ``declared_capabilities()``.
"""

from __future__ import annotations

from sopvm.capability.token import CapabilityToken, parse_capability

from .base import ToolProvider


class ProviderRegistry:
    """Registry of tool providers, matched by capability namespace+action."""

    def __init__(self) -> None:
        self._providers: list[ToolProvider] = []
        self._index: dict[tuple[str, str], ToolProvider] = {}

    def register(self, provider: ToolProvider) -> None:
        """Register a provider for all its declared capabilities.

        If a capability's namespace+action is already registered, the
        new provider overrides the old one.
        """
        self._providers.append(provider)
        for cap_str in provider.declared_capabilities():
            token = parse_capability(cap_str)
            self._index[(token.namespace, token.action)] = provider

    def lookup(self, capability: CapabilityToken) -> ToolProvider | None:
        """Find a provider that can handle the given capability.

        Returns the provider if one is registered for the capability's
        namespace+action, else None.
        """
        return self._index.get((capability.namespace, capability.action))

    @property
    def providers(self) -> list[ToolProvider]:
        """All registered providers."""
        return list(self._providers)
