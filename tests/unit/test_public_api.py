"""Tests for M13: Public API, IR version check, API compat."""

import pytest

from sopvm.ir.model import CompiledProgram, IrNode
from sopvm.runtime.executor import Executor, UnsupportedIrVersionError
from sopvm.runtime.state import StepState


class _AlwaysDone:
    def execute(self, node, request_tool=None) -> StepState:
        return StepState.DONE


class TestPublicAPI:
    def test_compile_exists(self):
        import sopvm
        assert callable(sopvm.compile)

    def test_check_exists(self):
        import sopvm
        assert callable(sopvm.check)

    def test_runtime_exists(self):
        import sopvm
        assert hasattr(sopvm, "Runtime")

    def test_compile_signature(self):
        import sopvm
        import inspect
        sig = inspect.signature(sopvm.compile)
        params = list(sig.parameters.keys())
        assert "sop_path" in params
        assert "policy_path" in params

    def test_check_signature(self):
        import sopvm
        import inspect
        sig = inspect.signature(sopvm.check)
        params = list(sig.parameters.keys())
        assert "compiled" in params

    def test_runtime_init_signature(self):
        import sopvm
        import inspect
        sig = inspect.signature(sopvm.Runtime.__init__)
        params = list(sig.parameters.keys())
        assert "compiled" in params
        assert "providers" in params


class TestIRVersionCheck:
    def test_supported_version_passes(self):
        prog = CompiledProgram(
            ir_version="0.1", entry="a",
            nodes={"a": IrNode(edges={}, terminal=True)},
        )
        result = Executor(prog, _AlwaysDone()).run()
        assert result.final_state == StepState.DONE

    def test_unsupported_version_raises(self):
        prog = CompiledProgram(
            ir_version="99.0", entry="a",
            nodes={"a": IrNode(edges={}, terminal=True)},
        )
        with pytest.raises(UnsupportedIrVersionError, match="99.0"):
            Executor(prog, _AlwaysDone()).run()

    def test_unsupported_version_error_message(self):
        prog = CompiledProgram(
            ir_version="2.0", entry="a",
            nodes={"a": IrNode(edges={}, terminal=True)},
        )
        with pytest.raises(UnsupportedIrVersionError) as exc_info:
            Executor(prog, _AlwaysDone()).run()
        assert "2.0" in str(exc_info.value)
        assert "0.1" in str(exc_info.value)


class TestCompileEndToEnd:
    def test_compile_returns_compiled_program(self):
        from sopvm import compile
        from pathlib import Path

        sop = Path("tests/fixtures/refund-request-handling.sop.yaml")
        policy = Path("policies/support-agent.policy.yaml")
        result = compile(str(sop), str(policy))
        assert isinstance(result, CompiledProgram)
        assert result.ir_version == "0.1"
