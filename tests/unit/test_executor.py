"""Unit tests for the runtime executor."""

from typing import Callable

import pytest

from sopvm.capability.token import CapabilityToken
from sopvm.ir.model import CompiledProgram, IrNode
from sopvm.runtime.events import Event
from sopvm.runtime.executor import Executor, ExecutorError, RunResult
from sopvm.runtime.state import StepState


class FakeHandler:
    """A configurable fake StepHandler for testing."""

    def __init__(self, results: dict[str, StepState] | None = None,
                 default: StepState = StepState.DONE):
        self._results = results or {}
        self._default = default
        self.call_count: dict[str, int] = {}

    def execute(self, node: IrNode,
                request_tool: Callable[[CapabilityToken, dict], object] | None = None) -> StepState:
        step_id = id(node)
        self.call_count[step_id] = self.call_count.get(step_id, 0) + 1
        count = self.call_count[step_id]
        if count in self._results:
            return self._results[count]
        return self._default


def _linear_program(*step_ids: str) -> CompiledProgram:
    """Build a linear chain: step1 -> step2 -> ... -> stepN (terminal)."""
    nodes = {}
    for i, sid in enumerate(step_ids):
        if i < len(step_ids) - 1:
            nodes[sid] = IrNode(
                capabilities_declared=[], capabilities_paged=[],
                edges={"on_success": step_ids[i + 1], "on_failure": step_ids[i + 1]},
                terminal=False,
            )
        else:
            nodes[sid] = IrNode(
                capabilities_declared=[], capabilities_paged=[],
                edges={}, terminal=True,
            )
    return CompiledProgram(ir_version="0.1", entry=step_ids[0], nodes=nodes)


def _branching_program() -> CompiledProgram:
    """Build: a --success--> b (terminal), a --failure--> c (terminal)."""
    return CompiledProgram(
        ir_version="0.1",
        entry="a",
        nodes={
            "a": IrNode(edges={"on_success": "b", "on_failure": "c"}, terminal=False),
            "b": IrNode(edges={}, terminal=True),
            "c": IrNode(edges={}, terminal=True),
        },
    )


class TestLinearExecution:
    def test_single_step_done(self):
        prog = _linear_program("a")
        handler = FakeHandler(default=StepState.DONE)
        result = Executor(prog, handler).run()
        assert result.final_state == StepState.DONE
        assert result.path == ("a",)

    def test_single_step_failed(self):
        prog = _linear_program("a")
        handler = FakeHandler(default=StepState.FAILED)
        result = Executor(prog, handler).run()
        assert result.final_state == StepState.FAILED
        assert result.path == ("a",)

    def test_linear_chain(self):
        prog = _linear_program("a", "b", "c")
        handler = FakeHandler(default=StepState.DONE)
        result = Executor(prog, handler).run()
        assert result.final_state == StepState.DONE
        assert result.path == ("a", "b", "c")

    def test_linear_chain_stops_on_failure(self):
        prog = _linear_program("a", "b", "c")
        handler = FakeHandler(default=StepState.FAILED)
        result = Executor(prog, handler).run()
        assert result.final_state == StepState.FAILED
        assert result.path == ("a", "b", "c")


class TestBranchingExecution:
    def test_success_path(self):
        prog = _branching_program()
        handler = FakeHandler(default=StepState.DONE)
        result = Executor(prog, handler).run()
        assert result.final_state == StepState.DONE
        assert result.path == ("a", "b")

    def test_failure_path(self):
        prog = _branching_program()
        handler = FakeHandler(default=StepState.FAILED)
        result = Executor(prog, handler).run()
        assert result.final_state == StepState.FAILED
        assert result.path == ("a", "c")

    def test_first_fails_second_succeeds(self):
        prog = _branching_program()
        handler = FakeHandler(default=StepState.FAILED)
        result = Executor(prog, handler).run()
        assert result.final_state == StepState.FAILED
        assert result.path == ("a", "c")


class TestEvents:
    def test_events_emitted(self):
        prog = _linear_program("a")
        events: list[Event] = []
        handler = FakeHandler(default=StepState.DONE)
        Executor(prog, handler, on_event=events.append).run()
        # M10 adds run_started and run_completed events
        assert len(events) == 4
        assert events[0].event == "run_started"
        assert events[1].event == "step_started"
        assert events[1].step_id == "a"
        assert events[2].event == "step_completed"
        assert events[2].step_id == "a"
        assert events[2].extra["state"] == "DONE"
        assert events[3].event == "run_completed"

    def test_events_for_chain(self):
        prog = _linear_program("a", "b")
        events: list[Event] = []
        handler = FakeHandler(default=StepState.DONE)
        Executor(prog, handler, on_event=events.append).run()
        started = [e for e in events if e.event == "step_started"]
        completed = [e for e in events if e.event == "step_completed"]
        assert len(started) == 2
        assert len(completed) == 2
        assert [e.step_id for e in started] == ["a", "b"]


class TestErrors:
    def test_missing_step_raises(self):
        prog = CompiledProgram(
            ir_version="0.1",
            entry="a",
            nodes={"a": IrNode(edges={"on_success": "nonexistent"}, terminal=False)},
        )
        handler = FakeHandler(default=StepState.DONE)
        with pytest.raises(ExecutorError, match="not found"):
            Executor(prog, handler).run()

    def test_missing_edge_raises(self):
        prog = CompiledProgram(
            ir_version="0.1",
            entry="a",
            nodes={"a": IrNode(edges={}, terminal=False)},
        )
        handler = FakeHandler(default=StepState.DONE)
        with pytest.raises(ExecutorError, match="no .* edge"):
            Executor(prog, handler).run()

    def test_step_limit_raises(self):
        prog = CompiledProgram(
            ir_version="0.1",
            entry="a",
            nodes={"a": IrNode(edges={"on_success": "a"}, terminal=False)},
        )
        handler = FakeHandler(default=StepState.DONE)
        with pytest.raises(ExecutorError, match="step limit"):
            Executor(prog, handler, max_steps=10).run()


class TestRunResult:
    def test_result_is_frozen(self):
        prog = _linear_program("a")
        handler = FakeHandler(default=StepState.DONE)
        result = Executor(prog, handler).run()
        assert isinstance(result, RunResult)
        assert result.final_state == StepState.DONE
        assert result.path == ("a",)
