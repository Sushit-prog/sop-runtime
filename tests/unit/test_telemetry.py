"""Unit tests for telemetry events and sinks."""

import json

import pytest

from sopvm.telemetry.events import Event, EventType, new_event
from sopvm.telemetry.sink import InMemorySink, JsonlSink


class TestEventType:
    def test_all_event_types_exist(self):
        expected = {
            "step_started", "step_completed", "step_failed",
            "capability_granted", "capability_denied",
            "run_started", "run_completed",
        }
        actual = {e.value for e in EventType}
        assert actual == expected


class TestEvent:
    def test_valid_event_type(self):
        e = Event(event="step_started", step_id="a",
                  timestamp="2026-01-01T00:00:00Z", run_id="r1")
        assert e.event == "step_started"

    def test_invalid_event_type_raises(self):
        with pytest.raises(ValueError, match="unknown event type"):
            Event(event="invalid_type", step_id="a",
                  timestamp="2026-01-01T00:00:00Z", run_id="r1")

    def test_new_event_auto_timestamp(self):
        e = new_event(EventType.STEP_STARTED, step_id="a", run_id="r1")
        assert e.event == "step_started"
        assert e.step_id == "a"
        assert e.run_id == "r1"
        assert "T" in e.timestamp  # ISO8601 format

    def test_new_event_with_string_type(self):
        e = new_event("step_completed", step_id="b", run_id="r2")
        assert e.event == "step_completed"

    def test_event_extra_fields(self):
        e = new_event(EventType.CAPABILITY_DENIED, step_id="x",
                      run_id="r1", extra={"requested": "fs:write(/tmp)"})
        assert e.extra["requested"] == "fs:write(/tmp)"


class TestInMemorySink:
    def test_emit_stores_events(self):
        sink = InMemorySink()
        e = new_event(EventType.STEP_STARTED, step_id="a", run_id="r1")
        sink.emit(e)
        assert len(sink.events) == 1
        assert sink.events[0] is e

    def test_multiple_emits(self):
        sink = InMemorySink()
        for i in range(5):
            sink.emit(new_event(EventType.STEP_STARTED, step_id=f"s{i}", run_id="r1"))
        assert len(sink.events) == 5


class TestJsonlSink:
    def test_emit_writes_jsonl(self, tmp_path):
        path = tmp_path / "trace.jsonl"
        sink = JsonlSink(path)
        e = new_event(EventType.CAPABILITY_DENIED, step_id="x",
                      run_id="r1", extra={"requested": "fs:write"})
        sink.emit(e)
        lines = path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["event"] == "capability_denied"
        assert record["step_id"] == "x"
        assert record["run_id"] == "r1"
        assert record["requested"] == "fs:write"

    def test_multiple_emits_append(self, tmp_path):
        path = tmp_path / "trace.jsonl"
        sink = JsonlSink(path)
        for i in range(3):
            sink.emit(new_event(EventType.STEP_STARTED, step_id=f"s{i}", run_id="r1"))
        lines = path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 3

    def test_sink_failure_does_not_crash_run(self):
        """Telemetry failure must not crash the run — executor completes."""
        from sopvm.ir.model import CompiledProgram, IrNode
        from sopvm.runtime.executor import Executor
        from sopvm.runtime.state import StepState

        class BrokenSink:
            def emit(self, event):
                raise RuntimeError("disk full")

        class AlwaysDone:
            def execute(self, node, request_tool=None):
                return StepState.DONE

        prog = CompiledProgram(
            ir_version="0.1",
            entry="a",
            nodes={"a": IrNode(edges={}, terminal=True)},
        )
        # Run with a sink that raises on every emit — must not crash
        result = Executor(prog, AlwaysDone(), sink=BrokenSink()).run()
        assert result.final_state == StepState.DONE
        assert result.path == ("a",)
