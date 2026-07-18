"""Adversarial security-boundary tests for the capability gate.

Each test case represents a specific escalation technique an attacker
might use to bypass the capability gate at runtime.
"""

from typing import Callable

from sopvm.capability.token import CapabilityToken, parse_capability
from sopvm.ir.model import CompiledProgram, IrNode
from sopvm.runtime.executor import Executor, RunResult
from sopvm.runtime.state import StepState


def _program_with_caps(step_id: str, paged: list[str]) -> CompiledProgram:
    return CompiledProgram(
        ir_version="0.1",
        entry=step_id,
        nodes={
            step_id: IrNode(
                capabilities_declared=list(paged),
                capabilities_paged=list(paged),
                edges={},
                terminal=True,
            ),
        },
    )


class DenyAllHandler:
    """Handler that requests a specific out-of-scope capability."""
    def __init__(self, request_cap: str):
        self._cap = parse_capability(request_cap)
        self.denied = False

    def execute(self, node: IrNode,
                request_tool: Callable[[CapabilityToken], bool] | None = None) -> StepState:
        if request_tool and not request_tool(self._cap):
            self.denied = True
            return StepState.DENIED
        return StepState.DONE


# --- Out-of-scope capability call across namespaces -------------------------
# Step is paged for db:read, but handler requests fs:write — different namespace.
def test_out_of_scope_different_namespace():
    prog = _program_with_caps("a", ["db:read(orders)"])
    handler = DenyAllHandler("fs:write(/tmp)")
    result = Executor(prog, handler).run()
    assert result.final_state == StepState.DENIED
    assert handler.denied is True
    assert result.violation is not None
    assert "fs:write" in result.violation.requested.raw


# --- Out-of-scope capability call, same namespace, different action ---------
# Step is paged for db:read, but handler requests db:write.
def test_out_of_scope_same_namespace_different_action():
    prog = _program_with_caps("a", ["db:read(orders)"])
    handler = DenyAllHandler("db:write(orders)")
    result = Executor(prog, handler).run()
    assert result.final_state == StepState.DENIED
    assert handler.denied is True
    assert result.violation is not None
    assert "db:write" in result.violation.requested.raw


# --- Near-miss: param value differs from paged ceiling ----------------------
# Step is paged for max_amount<=100, handler requests max_amount=250.
def test_near_miss_param_value_exceeds_ceiling():
    prog = _program_with_caps("a", ["payments:refund(max_amount<=100.00)"])
    handler = DenyAllHandler("payments:refund(max_amount=250.00)")
    result = Executor(prog, handler).run()
    assert result.final_state == StepState.DENIED
    assert handler.denied is True
    assert result.violation is not None
    assert "250" in result.violation.requested.raw


# --- Near-miss: param name differs from paged entry ------------------------
# Step is paged for max_amount<=100, handler requests max_amount_v2=50.
def test_near_miss_param_name_differs():
    prog = _program_with_caps("a", ["payments:refund(max_amount<=100.00)"])
    handler = DenyAllHandler("payments:refund(max_amount_v2=50.00)")
    result = Executor(prog, handler).run()
    assert result.final_state == StepState.DENIED
    assert handler.denied is True


# --- Correctly within scope: must NOT be denied ----------------------------
# Step is paged for db:read(orders), handler requests the same — must pass.
def test_within_scope_not_denied():
    prog = _program_with_caps("a", ["db:read(orders)"])

    class AllowAllHandler:
        def __init__(self):
            self.allowed = False
        def execute(self, node: IrNode,
                    request_tool: Callable[[CapabilityToken], bool] | None = None) -> StepState:
            if request_tool:
                self.allowed = request_tool(parse_capability("db:read(orders)"))
            return StepState.DONE

    handler = AllowAllHandler()
    result = Executor(prog, handler).run()
    assert result.final_state == StepState.DONE
    assert handler.allowed is True
    assert result.violation is None


# --- Multiple capabilities: one allowed, one denied -------------------------
# Step is paged for db:read AND notify:email. Handler requests db:read (ok),
# then notify:slack (denied).
def test_multiple_caps_one_denied():
    prog = CompiledProgram(
        ir_version="0.1",
        entry="a",
        nodes={
            "a": IrNode(
                capabilities_declared=["db:read(orders)", "notify:email"],
                capabilities_paged=["db:read(orders)", "notify:email"],
                edges={},
                terminal=True,
            ),
        },
    )

    class MultiCapHandler:
        def __init__(self):
            self.first_ok = False
            self.second_denied = False
        def execute(self, node: IrNode,
                    request_tool: Callable[[CapabilityToken], bool] | None = None) -> StepState:
            if request_tool:
                self.first_ok = request_tool(parse_capability("db:read(orders)"))
                if not request_tool(parse_capability("notify:slack(channel=general)")):
                    self.second_denied = True
                    return StepState.DENIED
            return StepState.DONE

    handler = MultiCapHandler()
    result = Executor(prog, handler).run()
    assert result.final_state == StepState.DENIED
    assert handler.first_ok is True
    assert handler.second_denied is True
    assert result.violation is not None
    assert "notify:slack" in result.violation.requested.raw


# --- Capability_denied event emitted on denial -----------------------------
def test_denied_event_emitted():
    from sopvm.runtime.events import Event
    prog = _program_with_caps("a", ["db:read(orders)"])
    handler = DenyAllHandler("fs:write(/tmp)")
    events: list[Event] = []
    Executor(prog, handler, on_event=events.append).run()
    denied_events = [e for e in events if e.event_type == "capability_denied"]
    assert len(denied_events) == 1
    assert denied_events[0].step_id == "a"
    assert "fs:write" in denied_events[0].extra["requested"]
