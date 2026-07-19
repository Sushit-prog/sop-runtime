"""Integration test: full SOP run with telemetry trace verification.

Runs the example SOP end-to-end and asserts the resulting telemetry
trace contains the expected sequence of event types in order.
"""

from pathlib import Path

import pytest

from sopvm.compiler.pipeline import compile_sop
from sopvm.runtime.executor import Executor
from sopvm.runtime.state import StepState
from sopvm.telemetry.events import EventType
from sopvm.telemetry.sink import InMemorySink

FIXTURE_SOP = Path(__file__).resolve().parents[1] / "fixtures" / "refund-request-handling.sop.yaml"
FIXTURE_POLICY = Path(__file__).resolve().parents[1].parent / "policies" / "support-agent.policy.yaml"


class _AlwaysDoneHandler:
    def execute(self, node, request_tool=None) -> StepState:
        return StepState.DONE


class TestTelemetryTrace:
    @pytest.fixture(scope="class")
    def trace(self):
        compiled = compile_sop(str(FIXTURE_SOP), str(FIXTURE_POLICY))
        sink = InMemorySink()
        handler = _AlwaysDoneHandler()
        result = Executor(compiled, handler, sink=sink).run()
        return result, sink.events

    def test_run_started_emitted(self, trace):
        _, events = trace
        assert events[0].event == EventType.RUN_STARTED.value

    def test_run_completed_emitted(self, trace):
        _, events = trace
        assert events[-1].event == EventType.RUN_COMPLETED.value

    def test_step_events_in_order(self, trace):
        _, events = trace
        step_events = [e for e in events if e.event.startswith("step_")]
        # Each step should have started then completed
        started = [e for e in step_events if e.event == "step_started"]
        completed = [e for e in step_events if e.event == "step_completed"]
        assert len(started) == len(completed)
        # 5 steps in the SOP, but only 4 executed (notify_user is terminal,
        # escalate_human is never reached)
        assert len(started) == 4

    def test_step_ids_match_path(self, trace):
        result, events = trace
        step_events = [e for e in events if e.event == "step_started"]
        step_ids = [e.step_id for e in step_events]
        assert step_ids == list(result.path)

    def test_all_events_have_run_id(self, trace):
        _, events = trace
        for event in events:
            assert event.run_id, f"event {event.event} missing run_id"

    def test_all_events_have_timestamp(self, trace):
        _, events = trace
        for event in events:
            assert event.timestamp, f"event {event.event} missing timestamp"

    def test_run_result_has_run_id(self, trace):
        result, _ = trace
        assert result.run_id

    def test_events_share_same_run_id(self, trace):
        _, events = trace
        run_ids = {e.run_id for e in events}
        assert len(run_ids) == 1


class TestDeniedCapabilityTrace:
    def test_denied_event_has_correct_details(self):
        from sopvm.capability.token import parse_capability
        from sopvm.ir.model import CompiledProgram, IrNode

        prog = CompiledProgram(
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

        class DenyHandler:
            def execute(self, node, request_tool=None) -> StepState:
                if request_tool:
                    result = request_tool(parse_capability("fs:write(/tmp)"), {})
                    if not result.success:
                        return StepState.DENIED
                return StepState.DONE

        sink = InMemorySink()
        result = Executor(prog, DenyHandler(), sink=sink).run()

        assert result.final_state == StepState.DENIED
        denied = [e for e in sink.events if e.event == "capability_denied"]
        assert len(denied) == 1
        assert denied[0].step_id == "a"
        assert denied[0].extra["requested"] == "fs:write(/tmp)"
        assert "db:read(orders)" in denied[0].extra["paged"]
