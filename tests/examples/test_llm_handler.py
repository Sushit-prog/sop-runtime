"""Integration tests for the LLM StepHandler with mocked LLM responses.

These tests verify the handler correctly translates model decisions into
request_tool() calls and correctly handles DENIED responses from the gate.
No actual model file is required — the LLM is mocked at the create_chat_completion
level.
"""

from __future__ import annotations

import json
from typing import Any, Callable
from unittest.mock import MagicMock, patch

import pytest

from sopvm.capability.token import CapabilityToken, parse_capability
from sopvm.ir.model import CompiledProgram, IrNode
from sopvm.plugins.base import ToolResult
from sopvm.runtime.executor import Executor
from sopvm.runtime.state import StepState


# --- Mock LLM handler ---

class MockLlamaHandler:
    """A StepHandler that mimics LlamaHandler with pre-scripted LLM responses.

    Instead of calling a real model, it uses a list of scripted responses
    that simulate what the LLM would return.
    """

    def __init__(self, responses: list[dict[str, Any]]):
        """
        Args:
            responses: List of dicts with keys "tool", "args", "reasoning".
                       Each response is used in order for each execute() call.
        """
        self._responses = list(responses)
        self._call_index = 0
        self.calls: list[dict[str, Any]] = []

    def execute(
        self,
        node: IrNode,
        request_tool: Callable[[CapabilityToken, dict], ToolResult],
    ) -> StepState:
        """Execute a step using a pre-scripted LLM response."""
        if self._call_index >= len(self._responses):
            raise RuntimeError("No more scripted responses available")

        decision = self._responses[self._call_index]
        self._call_index += 1
        self.calls.append(decision)

        tool_str = decision.get("tool")
        args = decision.get("args", {})

        if tool_str is None:
            return StepState.DONE

        # Attempt to invoke the requested tool via the gate
        try:
            cap = parse_capability(tool_str)
        except Exception:
            return StepState.FAILED

        result = request_tool(cap, args)

        if result.success:
            return StepState.DONE
        else:
            return StepState.FAILED


# --- Test fixtures ---

def _simple_program() -> CompiledProgram:
    """A simple linear program: a -> b (terminal)."""
    return CompiledProgram(
        ir_version="0.1",
        entry="a",
        nodes={
            "a": IrNode(
                capabilities_declared=["db:read(orders)"],
                capabilities_paged=["db:read(orders)"],
                edges={"on_success": "b"},
            ),
            "b": IrNode(
                capabilities_declared=["notify:email"],
                capabilities_paged=["notify:email"],
                edges={},
                terminal=True,
            ),
        },
    )


def _conditional_program() -> CompiledProgram:
    """Program with conditional branching: check -> yes/no."""
    return CompiledProgram(
        ir_version="0.1",
        entry="check",
        nodes={
            "check": IrNode(
                capabilities_declared=["db:read(orders)"],
                capabilities_paged=["db:read(orders)"],
                condition="Is the order valid?",
                edges={"on_success": "yes", "on_failure": "no"},
            ),
            "yes": IrNode(
                capabilities_declared=["notify:email"],
                capabilities_paged=["notify:email"],
                edges={},
                terminal=True,
            ),
            "no": IrNode(
                capabilities_declared=["notify:email"],
                capabilities_paged=["notify:email"],
                edges={},
                terminal=True,
            ),
        },
    )


# --- Tests ---

class TestMockHandlerBasic:
    def test_no_tool_call_returns_done(self):
        """Handler with no tool call returns DONE."""
        responses = [
            {"tool": None, "args": {}, "reasoning": "no tool needed"},
            {"tool": None, "args": {}, "reasoning": "done"},
        ]
        handler = MockLlamaHandler(responses)
        prog = _simple_program()
        result = Executor(prog, handler).run()
        assert result.final_state == StepState.DONE
        assert result.path == ("a", "b")

    def test_successful_tool_call_returns_done(self):
        """Handler with successful tool call returns DONE."""
        responses = [
            {"tool": "db:read(orders)", "args": {"resource": "orders"}, "reasoning": "reading orders"},
            {"tool": None, "args": {}, "reasoning": "done"},
        ]
        handler = MockLlamaHandler(responses)
        prog = _simple_program()
        result = Executor(prog, handler).run()
        assert result.final_state == StepState.DONE
        assert len(handler.calls) == 2
        assert handler.calls[0]["tool"] == "db:read(orders)"


class TestMockHandlerConditionals:
    def test_condition_true_takes_yes_path(self):
        """When LLM returns DONE for a conditional step, takes on_success path."""
        responses = [
            {"tool": "db:read(orders)", "args": {}, "reasoning": "order is valid"},
            {"tool": None, "args": {}, "reasoning": "done"},
        ]
        handler = MockLlamaHandler(responses)
        prog = _conditional_program()
        result = Executor(prog, handler).run()
        assert result.path == ("check", "yes")

    def test_condition_false_takes_no_path(self):
        """When LLM returns FAILED for a conditional step, takes on_failure path."""
        responses = [
            {"tool": None, "args": {}, "reasoning": "order is not valid"},
            {"tool": None, "args": {}, "reasoning": "done"},
        ]

        class FailFirst:
            """Returns FAILED for the first step (condition false)."""
            def __init__(self):
                self._calls = 0
            def execute(self, node, request_tool=None):
                self._calls += 1
                if self._calls == 1:
                    return StepState.FAILED
                return StepState.DONE

        handler = FailFirst()
        prog = _conditional_program()
        result = Executor(prog, handler).run()
        assert result.path == ("check", "no")


class TestGateEnforcement:
    def test_denied_tool_call_returns_failed(self):
        """When request_tool returns a denied result, handler returns FAILED."""
        class DenyHandler:
            """Always tries an out-of-scope capability."""
            def execute(self, node, request_tool=None):
                cap = parse_capability("fs:write(/etc/passwd)")
                result = request_tool(cap, {})
                if not result.success:
                    return StepState.FAILED
                return StepState.DONE

        prog = _simple_program()
        handler = DenyHandler()
        result = Executor(prog, handler).run()
        # The gate denies fs:write, handler returns FAILED, follows on_failure
        # Since there's no on_failure edge, this raises ExecutorError
        assert result.final_state == StepState.DENIED or result.final_state == StepState.FAILED

    def test_out_of_scope_capability_denied(self):
        """Capability not in capabilities_paged is denied by the gate."""
        prog = CompiledProgram(
            ir_version="0.1",
            entry="a",
            nodes={
                "a": IrNode(
                    capabilities_declared=["db:read(orders)"],
                    capabilities_paged=["db:read(orders)"],
                    edges={"on_success": "b"},
                ),
                "b": IrNode(terminal=True),
            },
        )

        class OutOfScopeHandler:
            def execute(self, node, request_tool=None):
                # Try to invoke fs:write — not in capabilities_paged
                cap = parse_capability("fs:write(/tmp)")
                result = request_tool(cap, {})
                if not result.success:
                    return StepState.DENIED
                return StepState.DONE

        handler = OutOfScopeHandler()
        result = Executor(prog, handler).run()
        assert result.final_state == StepState.DENIED
        assert result.violation is not None


class TestHandlerProtocol:
    def test_handler_is_protocol_compliant(self):
        """MockLlamaHandler satisfies the StepHandler protocol."""
        from sopvm.runtime.executor import StepHandler
        handler = MockLlamaHandler([])
        assert isinstance(handler, StepHandler)
