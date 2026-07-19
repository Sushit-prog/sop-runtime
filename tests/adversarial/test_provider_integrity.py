"""Adversarial tests: provider integrity vs SOP-level gate (defense in depth).

These tests prove that the M7 gate and the M8 sandbox are two
genuinely independent checks. Even if the M7 gate had a bug, the
sandbox would still catch a lying provider.
"""

from typing import Callable

import pytest

from sopvm.capability.token import CapabilityToken, parse_capability
from sopvm.ir.model import CompiledProgram, IrNode
from sopvm.plugins.base import ToolResult
from sopvm.plugins.sandbox import ProviderIntegrityViolation, wrap_provider
from sopvm.runtime.executor import Executor
from sopvm.runtime.state import StepState


class LyingProvider:
    """Provider that declares db:read but tries to invoke fs:write."""
    def declared_capabilities(self) -> list[str]:
        return ["db:read(orders)"]

    def invoke(self, capability: CapabilityToken, args: dict) -> ToolResult:
        # This should never be reached if sandbox is working
        return ToolResult(success=True, data={"hacked": True})


# --- Provider lying about its scope — caught by sandbox independently -------
def test_sandbox_catches_lying_provider_without_gate():
    """Proves sandbox works independently of the M7 gate."""
    lying = LyingProvider()
    sandboxed = wrap_provider(lying)
    cap = parse_capability("fs:write(/tmp)")
    with pytest.raises(ProviderIntegrityViolation):
        sandboxed.invoke(cap, {})


# --- Provider lying + gate passes — sandbox still catches it ---------------
def test_sandbox_catches_lying_provider_even_if_gate_bypassed():
    """If the gate has a bug and lets an invalid call through, sandbox catches it.

    Simulate: register lying provider, page db:read for the step, but the
    handler requests fs:write (which the gate would deny). We simulate a
    gate bypass by having the handler NOT use request_tool at all — instead
    it calls the provider directly. The sandbox catches this.
    """
    lying = LyingProvider()
    sandboxed = wrap_provider(lying)
    # The lying provider tries to invoke fs:write — outside its declared scope
    cap = parse_capability("fs:write(/tmp)")
    try:
        sandboxed.invoke(cap, {})
        assert False, "should have raised"
    except ProviderIntegrityViolation as e:
        assert "fs:write" in str(e)
        assert e.provider is lying


# --- Gate blocks lying provider — sandbox is defense in depth ---------------
def test_gate_blocks_lying_provider_at_executor_level():
    """Gate blocks the call, sandbox is the second layer."""
    prog = CompiledProgram(
        ir_version="0.1",
        entry="a",
        nodes={
            "a": IrNode(
                capabilities_declared=["db:read(orders)"],
                capabilities_paged=["db:read(orders)"],
                terminal=True,
            ),
        },
    )

    class LyingHandler:
        def execute(self, node: IrNode,
                    request_tool: Callable[[CapabilityToken, dict], ToolResult] | None = None) -> StepState:
            if request_tool:
                # Try to invoke fs:write — gate should deny this
                result = request_tool(parse_capability("fs:write(/tmp)"), {})
                if not result.success:
                    return StepState.DENIED
            return StepState.DONE

    handler = LyingHandler()
    result = Executor(prog, handler).run()
    assert result.final_state == StepState.DENIED
    assert result.violation is not None
    assert "fs:write" in result.violation.requested.raw


# --- Provider within scope — must NOT be denied by sandbox -----------------
def test_provider_within_scope_not_sandbox_denied():
    """A provider invoking its own declared capability passes sandbox."""
    class HonestProvider:
        def declared_capabilities(self) -> list[str]:
            return ["db:read(orders)"]
        def invoke(self, capability: CapabilityToken, args: dict) -> ToolResult:
            return ToolResult(success=True, data={"rows": [1, 2, 3]})

    honest = HonestProvider()
    sandboxed = wrap_provider(honest)
    cap = parse_capability("db:read(orders)")
    result = sandboxed.invoke(cap, {})
    assert result.success is True
    assert result.data == {"rows": [1, 2, 3]}
