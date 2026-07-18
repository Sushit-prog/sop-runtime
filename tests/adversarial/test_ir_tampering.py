"""Adversarial tests: IR tampering (Milestone 12).

Tests that the runtime catches hand-edited IR JSON files with
capabilities_paged entries that the compiler would never have emitted.

This is defense-in-depth: the IR is no longer trusted at face value.
If a policy was provided at Executor construction time, the runtime
re-validates capabilities_paged against the policy before execution.
"""

import json

import pytest

from sopvm.capability.policy import Policy
from sopvm.capability.token import parse_capability
from sopvm.ir.model import CompiledProgram, IrNode
from sopvm.runtime.executor import Executor, ExecutorError
from sopvm.runtime.state import StepState


class _AlwaysDone:
    def execute(self, node, request_tool=None) -> StepState:
        return StepState.DONE


def _tampered_program() -> CompiledProgram:
    """Build a program with tampered capabilities_paged."""
    return CompiledProgram(
        ir_version="0.1",
        entry="a",
        nodes={
            "a": IrNode(
                capabilities_declared=["db:read(orders)"],
                # Tampered: paged capability not allowed by policy
                capabilities_paged=["db:read(orders)", "fs:write(/etc/shadow)"],
                edges={},
                terminal=True,
            ),
        },
    )


def _valid_program() -> CompiledProgram:
    """Build a program with valid capabilities_paged."""
    return CompiledProgram(
        ir_version="0.1",
        entry="a",
        nodes={
            "a": IrNode(
                capabilities_declared=["db:read(orders)", "fs:write(/tmp)"],
                capabilities_paged=["db:read(orders)", "fs:write(/tmp)"],
                edges={},
                terminal=True,
            ),
        },
    )


class TestIRTampering:
    def test_tampered_paged_capabilities_rejected(self):
        """Hand-edited IR with unauthorized paged capability is caught."""
        prog = _tampered_program()
        policy = Policy(
            policy_version="0.1",
            allowed_capabilities=(parse_capability("db:read(orders)"),),
        )
        with pytest.raises(ExecutorError, match="IR tampering detected"):
            Executor(prog, _AlwaysDone(), policy=policy).run()

    def test_tampered_paged_subset_accepted(self):
        """Narrowing paged capabilities (subset of declared) is valid."""
        prog = CompiledProgram(
            ir_version="0.1",
            entry="a",
            nodes={
                "a": IrNode(
                    capabilities_declared=["db:read(orders)", "fs:write(/tmp)"],
                    # Paged is a subset of declared — valid narrowing
                    capabilities_paged=["db:read(orders)"],
                    edges={},
                    terminal=True,
                ),
            },
        )
        policy = Policy(
            policy_version="0.1",
            allowed_capabilities=(
                parse_capability("db:read(orders)"),
                parse_capability("fs:write(/tmp)"),
            ),
        )
        result = Executor(prog, _AlwaysDone(), policy=policy).run()
        assert result.final_state == StepState.DONE

    def test_no_policy_skips_validation(self):
        """Without a policy, validation is skipped (backwards compat)."""
        prog = _tampered_program()
        # No policy — should not raise
        result = Executor(prog, _AlwaysDone()).run()
        assert result.final_state == StepState.DONE

    def test_tampered_via_json_roundtrip(self):
        """Simulate IR tampering via JSON edit then reload."""
        original = CompiledProgram(
            ir_version="0.1",
            entry="a",
            nodes={
                "a": IrNode(
                    capabilities_declared=["db:read(orders)"],
                    capabilities_paged=["db:read(orders)"],
                    edges={},
                    terminal=True,
                ),
            },
        )
        # Serialize, tamper, deserialize
        json_str = original.to_json()
        data = json.loads(json_str)
        data["nodes"]["a"]["capabilities_paged"].append("fs:write(/etc/passwd)")
        tampered = CompiledProgram.from_json(json.dumps(data))

        policy = Policy(
            policy_version="0.1",
            allowed_capabilities=(parse_capability("db:read(orders)"),),
        )
        with pytest.raises(ExecutorError, match="IR tampering detected"):
            Executor(tampered, _AlwaysDone(), policy=policy).run()
