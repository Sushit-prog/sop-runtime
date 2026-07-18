"""Property-based tests for the executor."""

from typing import Callable

import hypothesis.strategies as st
from hypothesis import given, settings

from sopvm.capability.token import CapabilityToken
from sopvm.ir.model import CompiledProgram, IrNode
from sopvm.runtime.executor import Executor, ExecutorError
from sopvm.runtime.state import StepState


_step_id = st.from_regex(r"[a-z]{1,6}", fullmatch=True)


class AlwaysDone:
    """Handler that always returns DONE."""
    def execute(self, node: IrNode,
                request_tool: Callable[[CapabilityToken, dict], object] | None = None) -> StepState:
        return StepState.DONE


class AlwaysFail:
    """Handler that always returns FAILED."""
    def execute(self, node: IrNode,
                request_tool: Callable[[CapabilityToken, dict], object] | None = None) -> StepState:
        return StepState.FAILED


def _linear_program(ids: list[str]) -> CompiledProgram:
    nodes = {}
    for i, sid in enumerate(ids):
        if i < len(ids) - 1:
            nodes[sid] = IrNode(
                edges={"on_success": ids[i + 1], "on_failure": ids[i + 1]},
                terminal=False,
            )
        else:
            nodes[sid] = IrNode(edges={}, terminal=True)
    return CompiledProgram(ir_version="0.1", entry=ids[0], nodes=nodes)


@given(step_ids=st.lists(_step_id, min_size=1, max_size=8, unique=True))
@settings(max_examples=200, deadline=None)
def test_linear_program_terminates_with_done(step_ids):
    """Any linear program terminates with DONE when handler always succeeds."""
    prog = _linear_program(step_ids)
    result = Executor(prog, AlwaysDone()).run()
    assert result.final_state == StepState.DONE
    assert result.path == tuple(step_ids)


@given(step_ids=st.lists(_step_id, min_size=1, max_size=8, unique=True))
@settings(max_examples=200, deadline=None)
def test_linear_program_terminates_with_failed(step_ids):
    """Any linear program terminates with FAILED when handler always fails."""
    prog = _linear_program(step_ids)
    result = Executor(prog, AlwaysFail()).run()
    assert result.final_state == StepState.FAILED
    assert result.path == tuple(step_ids)


@given(step_ids=st.lists(_step_id, min_size=1, max_size=8, unique=True))
@settings(max_examples=200, deadline=None)
def test_run_result_never_pending_or_running(step_ids):
    """RunResult.final_state is never PENDING or RUNNING."""
    prog = _linear_program(step_ids)
    for handler in (AlwaysDone(), AlwaysFail()):
        result = Executor(prog, handler).run()
        assert result.final_state not in (StepState.PENDING, StepState.RUNNING)
        assert result.final_state in (StepState.DONE, StepState.FAILED, StepState.DENIED)


@given(step_ids=st.lists(_step_id, min_size=2, max_size=8, unique=True))
@settings(max_examples=200, deadline=None)
def test_branching_program_terminates(step_ids):
    """A branching program where first step always fails terminates quickly."""
    nodes = {}
    for i, sid in enumerate(step_ids):
        if i == 0:
            nodes[sid] = IrNode(edges={"on_failure": step_ids[1]}, terminal=False)
        elif i == 1:
            nodes[sid] = IrNode(edges={}, terminal=True)
        else:
            nodes[sid] = IrNode(edges={}, terminal=True)

    prog = CompiledProgram(ir_version="0.1", entry=step_ids[0], nodes=nodes)
    result = Executor(prog, AlwaysFail()).run()
    assert result.final_state == StepState.FAILED
    assert result.path == (step_ids[0], step_ids[1])
