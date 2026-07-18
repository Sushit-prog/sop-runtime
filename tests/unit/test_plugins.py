"""Unit tests for the plugin architecture."""

import pytest

from sopvm.capability.token import parse_capability
from sopvm.plugins.base import ToolResult
from sopvm.plugins.registry import ProviderRegistry
from sopvm.plugins.sandbox import ProviderIntegrityViolation, wrap_provider


class SimpleProvider:
    """A simple test provider."""
    def __init__(self, caps: list[str]):
        self._caps = caps

    def declared_capabilities(self) -> list[str]:
        return self._caps

    def invoke(self, capability, args) -> ToolResult:
        return ToolResult(success=True, data={"echo": capability.raw})


class LyingProvider:
    """A provider that invokes capabilities it didn't declare."""
    def declared_capabilities(self) -> list[str]:
        return ["db:read(orders)"]

    def invoke(self, capability, args) -> ToolResult:
        # Lies: invokes a capability it didn't declare
        return ToolResult(success=True, data={"hacked": True})


class TestProviderRegistry:
    def test_register_and_lookup(self):
        reg = ProviderRegistry()
        prov = SimpleProvider(["db:read(orders)", "notify:email"])
        reg.register(prov)
        cap = parse_capability("db:read(orders)")
        assert reg.lookup(cap) is prov

    def test_lookup_missing(self):
        reg = ProviderRegistry()
        reg.register(SimpleProvider(["db:read(orders)"]))
        cap = parse_capability("fs:write(/tmp)")
        assert reg.lookup(cap) is None

    def test_lookup_by_namespace_action(self):
        reg = ProviderRegistry()
        prov = SimpleProvider(["payments:refund(max_amount<=100.00)"])
        reg.register(prov)
        cap = parse_capability("payments:refund(max_amount=50.00)")
        assert reg.lookup(cap) is prov

    def test_override_on_re_register(self):
        reg = ProviderRegistry()
        prov1 = SimpleProvider(["db:read(orders)"])
        prov2 = SimpleProvider(["db:read(orders)"])
        reg.register(prov1)
        reg.register(prov2)
        cap = parse_capability("db:read(orders)")
        assert reg.lookup(cap) is prov2

    def test_providers_property(self):
        reg = ProviderRegistry()
        p1 = SimpleProvider(["a:a"])
        p2 = SimpleProvider(["b:b"])
        reg.register(p1)
        reg.register(p2)
        assert reg.providers == [p1, p2]


class TestSandbox:
    def test_wrap_allows_declared(self):
        prov = SimpleProvider(["db:read(orders)"])
        sandboxed = wrap_provider(prov)
        cap = parse_capability("db:read(orders)")
        result = sandboxed.invoke(cap, {})
        assert result.success is True

    def test_wrap_blocks_undeclared(self):
        prov = LyingProvider()
        sandboxed = wrap_provider(prov)
        cap = parse_capability("fs:write(/tmp)")
        with pytest.raises(ProviderIntegrityViolation):
            sandboxed.invoke(cap, {})

    def test_wrap_preserves_declared_capabilities(self):
        prov = SimpleProvider(["db:read(orders)", "notify:email"])
        sandboxed = wrap_provider(prov)
        assert sandboxed.declared_capabilities() == ["db:read(orders)", "notify:email"]

    def test_violation_carries_provider_and_capability(self):
        prov = LyingProvider()
        sandboxed = wrap_provider(prov)
        cap = parse_capability("fs:write(/tmp)")
        with pytest.raises(ProviderIntegrityViolation) as exc_info:
            sandboxed.invoke(cap, {})
        assert exc_info.value.provider is prov
        assert exc_info.value.capability is cap
