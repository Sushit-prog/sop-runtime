"""Property-based tests for the capability gate."""

from typing import Callable

import hypothesis.strategies as st
from hypothesis import given, settings

from sopvm.capability.token import CapabilityToken, parse_capability
from sopvm.ir.model import CompiledProgram, IrNode
from sopvm.runtime.executor import Executor
from sopvm.runtime.state import StepState


_step_id = st.from_regex(r"[a-z]{1,6}", fullmatch=True)
_cap_str = st.from_regex(r"[a-z]{1,8}:[a-z]{1,8}", fullmatch=True)


class GateTestHandler:
    """Handler that requests a specific capability via the gate."""
    def __init__(self, cap: CapabilityToken):
        self._cap = cap
        self.approved = False

    def execute(self, node: IrNode,
                request_tool: Callable[[CapabilityToken, dict], object] | None = None) -> StepState:
        if request_tool:
            result = request_tool(self._cap, {})
            self.approved = getattr(result, 'success', False)
            if not self.approved:
                return StepState.DENIED
        return StepState.DONE


@given(
    step_id=_step_id,
    paged_caps=st.lists(_cap_str, min_size=0, max_size=6),
    request_cap=_cap_str,
)
@settings(max_examples=200, deadline=None)
def test_gate_approve_implies_paged_subset(step_id, paged_caps, request_cap):
    """If the gate approves a capability, it must satisfy at least one paged entry."""
    node = IrNode(
        capabilities_declared=list(paged_caps),
        capabilities_paged=list(paged_caps),
        terminal=True,
    )
    prog = CompiledProgram(
        ir_version="0.1",
        entry=step_id,
        nodes={step_id: node},
    )

    requested = parse_capability(request_cap)
    handler = GateTestHandler(requested)
    Executor(prog, handler).run()

    if handler.approved:
        # Gate approved — the capability must satisfy at least one paged entry
        from sopvm.checker.check import satisfies
        assert any(
            satisfies(requested, parse_capability(p))
            for p in paged_caps
        ), f"gate approved {request_cap!r} but it doesn't satisfy any paged entry"


@given(
    step_id=_step_id,
    paged_caps=st.lists(_cap_str, min_size=1, max_size=6),
    request_cap=_cap_str,
)
@settings(max_examples=200, deadline=None)
def test_gate_deny_implies_not_paged(step_id, paged_caps, request_cap):
    """If the gate denies a capability, it must not satisfy any paged entry."""
    node = IrNode(
        capabilities_declared=list(paged_caps),
        capabilities_paged=list(paged_caps),
        terminal=True,
    )
    prog = CompiledProgram(
        ir_version="0.1",
        entry=step_id,
        nodes={step_id: node},
    )

    requested = parse_capability(request_cap)
    handler = GateTestHandler(requested)
    Executor(prog, handler).run()

    if not handler.approved:
        # Gate denied — the capability must not satisfy any paged entry
        from sopvm.checker.check import satisfies
        assert not any(
            satisfies(requested, parse_capability(p))
            for p in paged_caps
        ), f"gate denied {request_cap!r} but it satisfies a paged entry"
