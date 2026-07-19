"""Tests for conditional branching and bounded loops."""

import json
import tempfile
from pathlib import Path

import pytest

from sopvm.compiler.lower import lower
from sopvm.ir.model import CompiledProgram, IrNode, IrLoop
from sopvm.parser import parse
from sopvm.parser.ast import SopDocument, StepNode, CapabilityRequest, LoopConfig
from sopvm.runtime.executor import Executor, ExecutorError
from sopvm.runtime.state import StepState


# --- Parser tests ---

class TestConditionalParsing:
    def test_condition_field_parsed(self, tmp_path):
        sop = tmp_path / "test.sop.yaml"
        sop.write_text("""
sop_version: "0.1"
name: "test"
policy: "p"
steps:
  - id: check
    description: "Check something"
    requires:
      capabilities: ["db:read(x)"]
    condition: "Is X true?"
    on_success: "yes"
    on_failure: "no"
  - id: "yes"
    terminal: true
    requires:
      capabilities: ["db:read(x)"]
  - id: "no"
    terminal: true
    requires:
      capabilities: ["db:read(x)"]
""")
        doc = parse(sop)
        check_step = doc.steps[0]
        assert check_step.condition == "Is X true?"
        assert check_step.edges == ("yes", "no")

    def test_loop_field_parsed(self, tmp_path):
        sop = tmp_path / "test.sop.yaml"
        sop.write_text("""
sop_version: "0.1"
name: "test"
policy: "p"
steps:
  - id: retry
    description: "Retry something"
    requires:
      capabilities: ["db:read(x)"]
    condition: "Is it working?"
    on_success: done
    on_failure: retry
    loop:
      max_iterations: 3
    on_limit: failed
  - id: done
    terminal: true
    requires:
      capabilities: ["db:read(x)"]
  - id: failed
    terminal: true
    requires:
      capabilities: ["db:read(x)"]
""")
        doc = parse(sop)
        retry_step = doc.steps[0]
        assert retry_step.loop is not None
        assert retry_step.loop.max_iterations == 3
        assert retry_step.on_limit == "failed"

    def test_on_limit_target_must_exist(self, tmp_path):
        sop = tmp_path / "test.sop.yaml"
        sop.write_text("""
sop_version: "0.1"
name: "test"
policy: "p"
steps:
  - id: retry
    requires:
      capabilities: ["db:read(x)"]
    condition: "Is it working?"
    on_success: done
    on_failure: retry
    loop:
      max_iterations: 3
    on_limit: nonexistent
  - id: done
    terminal: true
    requires:
      capabilities: ["db:read(x)"]
""")
        with pytest.raises(Exception, match="nonexistent"):
            parse(sop)


# --- IR lowering tests ---

class TestConditionalLowering:
    def test_condition_lowered_to_ir(self):
        doc = SopDocument(
            version="0.1",
            policy_ref="p",
            steps=(
                StepNode(
                    id="check",
                    description="Check",
                    requires=(CapabilityRequest(raw="db:read(x)"),),
                    edges=("yes", "no"),
                    terminal=False,
                    condition="Is X true?",
                ),
                StepNode(id="yes", description=None, requires=(), edges=(), terminal=True),
                StepNode(id="no", description=None, requires=(), edges=(), terminal=True),
            ),
        )
        prog = lower(doc)
        node = prog.nodes["check"]
        assert node.condition == "Is X true?"
        assert node.edges == {"on_success": "yes", "on_failure": "no"}

    def test_loop_lowered_to_ir(self):
        doc = SopDocument(
            version="0.1",
            policy_ref="p",
            steps=(
                StepNode(
                    id="retry",
                    description="Retry",
                    requires=(CapabilityRequest(raw="db:read(x)"),),
                    edges=("done", "retry"),
                    terminal=False,
                    condition="Is it working?",
                    loop=LoopConfig(max_iterations=3),
                    on_limit="failed",
                ),
                StepNode(id="done", description=None, requires=(), edges=(), terminal=True),
                StepNode(id="failed", description=None, requires=(), edges=(), terminal=True),
            ),
        )
        prog = lower(doc)
        node = prog.nodes["retry"]
        assert node.loop is not None
        assert node.loop.max_iterations == 3
        assert node.on_limit == "failed"


# --- Runtime executor tests ---

class _ConditionalHandler:
    """Handler that evaluates conditions based on a provided result map."""
    def __init__(self, results: dict[str, StepState]):
        self._results = results

    def execute(self, node, request_tool=None):
        # Use the condition string as the key for result lookup
        key = node.condition or "default"
        return self._results.get(key, StepState.DONE)


class TestConditionalExecution:
    def test_condition_true_follows_on_success(self):
        prog = CompiledProgram(
            ir_version="0.1",
            entry="check",
            nodes={
                "check": IrNode(
                    condition="Is X true?",
                    edges={"on_success": "yes", "on_failure": "no"},
                ),
                "yes": IrNode(terminal=True),
                "no": IrNode(terminal=True),
            },
        )
        handler = _ConditionalHandler({"Is X true?": StepState.DONE})
        result = Executor(prog, handler).run()
        assert result.final_state == StepState.DONE
        assert result.path == ("check", "yes")

    def test_condition_false_follows_on_failure(self):
        prog = CompiledProgram(
            ir_version="0.1",
            entry="check",
            nodes={
                "check": IrNode(
                    condition="Is X true?",
                    edges={"on_success": "yes", "on_failure": "no"},
                ),
                "yes": IrNode(terminal=True),
                "no": IrNode(terminal=True),
            },
        )
        handler = _ConditionalHandler({"Is X true?": StepState.FAILED})
        result = Executor(prog, handler).run()
        # Terminal step "no" executes and returns DONE — condition being
        # false just determines which path, not the final state
        assert result.final_state == StepState.DONE
        assert result.path == ("check", "no")


class TestLoopExecution:
    def test_loop_terminates_when_condition_met(self):
        """Loop exits when handler returns DONE (condition true)."""
        iteration = {"count": 0}

        class Handler:
            def execute(self, node, request_tool=None):
                iteration["count"] += 1
                # First two iterations: FAILED (condition false), third: DONE (true)
                if iteration["count"] >= 3:
                    return StepState.DONE
                return StepState.FAILED

        prog = CompiledProgram(
            ir_version="0.1",
            entry="retry",
            nodes={
                "retry": IrNode(
                    condition="Is it working?",
                    edges={"on_success": "done", "on_failure": "retry"},
                    loop=IrLoop(max_iterations=5),
                ),
                "done": IrNode(terminal=True),
            },
        )
        result = Executor(prog, Handler()).run()
        assert result.final_state == StepState.DONE
        # retry -> retry -> retry (3rd succeeds) -> done
        assert result.path == ("retry", "retry", "retry", "done")

    def test_loop_hits_max_iterations(self):
        """Loop terminates when max_iterations is exceeded."""
        class AlwaysFail:
            def execute(self, node, request_tool=None):
                return StepState.FAILED

        prog = CompiledProgram(
            ir_version="0.1",
            entry="retry",
            nodes={
                "retry": IrNode(
                    condition="Is it working?",
                    edges={"on_success": "done", "on_failure": "retry"},
                    loop=IrLoop(max_iterations=3),
                    on_limit="failed",
                ),
                "done": IrNode(terminal=True),
                "failed": IrNode(terminal=True),
            },
        )
        result = Executor(prog, AlwaysFail()).run()
        assert result.final_state == StepState.FAILED
        # retry -> retry -> retry (3 iterations) -> failed (on_limit)
        assert result.path == ("retry", "retry", "retry", "failed")

    def test_loop_without_on_limit_raises(self):
        """Loop exceeding max_iterations without on_limit edge raises error."""
        class AlwaysFail:
            def execute(self, node, request_tool=None):
                return StepState.FAILED

        prog = CompiledProgram(
            ir_version="0.1",
            entry="retry",
            nodes={
                "retry": IrNode(
                    condition="Is it working?",
                    edges={"on_success": "done", "on_failure": "retry"},
                    loop=IrLoop(max_iterations=2),
                    # No on_limit edge!
                ),
                "done": IrNode(terminal=True),
            },
        )
        with pytest.raises(ExecutorError, match="on_limit"):
            Executor(prog, AlwaysFail()).run()


# --- JSON roundtrip tests ---

class TestConditionalIRJson:
    def test_condition_roundtrip(self):
        prog = CompiledProgram(
            ir_version="0.1",
            entry="a",
            nodes={
                "a": IrNode(
                    condition="Is X true?",
                    edges={"on_success": "b", "on_failure": "c"},
                ),
                "b": IrNode(terminal=True),
                "c": IrNode(terminal=True),
            },
        )
        json_str = prog.to_json()
        restored = CompiledProgram.from_json(json_str)
        assert restored.nodes["a"].condition == "Is X true?"

    def test_loop_roundtrip(self):
        prog = CompiledProgram(
            ir_version="0.1",
            entry="a",
            nodes={
                "a": IrNode(
                    loop=IrLoop(max_iterations=5),
                    on_limit="b",
                    edges={"on_success": "a", "on_failure": "b"},
                ),
                "b": IrNode(terminal=True),
            },
        )
        json_str = prog.to_json()
        restored = CompiledProgram.from_json(json_str)
        assert restored.nodes["a"].loop is not None
        assert restored.nodes["a"].loop.max_iterations == 5
        assert restored.nodes["a"].on_limit == "b"


class TestCorruptMaxIterations:
    def test_string_max_iterations_rejected(self):
        """Non-integer max_iterations raises ValueError on deserialization."""
        ir_json = json.dumps({
            "ir_version": "0.1",
            "entry": "a",
            "nodes": {
                "a": {
                    "capabilities_declared": [],
                    "capabilities_paged": [],
                    "edges": {"on_success": "a"},
                    "terminal": False,
                    "loop": {"max_iterations": "abc"},
                },
            },
        })
        with pytest.raises(ValueError, match="invalid max_iterations"):
            CompiledProgram.from_json(ir_json)

    def test_negative_max_iterations_rejected(self):
        """Negative max_iterations raises ValueError on deserialization."""
        ir_json = json.dumps({
            "ir_version": "0.1",
            "entry": "a",
            "nodes": {
                "a": {
                    "capabilities_declared": [],
                    "capabilities_paged": [],
                    "edges": {"on_success": "a"},
                    "terminal": False,
                    "loop": {"max_iterations": -1},
                },
            },
        })
        with pytest.raises(ValueError, match="invalid max_iterations"):
            CompiledProgram.from_json(ir_json)

    def test_zero_max_iterations_rejected(self):
        """Zero max_iterations raises ValueError on deserialization."""
        ir_json = json.dumps({
            "ir_version": "0.1",
            "entry": "a",
            "nodes": {
                "a": {
                    "capabilities_declared": [],
                    "capabilities_paged": [],
                    "edges": {"on_success": "a"},
                    "terminal": False,
                    "loop": {"max_iterations": 0},
                },
            },
        })
        with pytest.raises(ValueError, match="invalid max_iterations"):
            CompiledProgram.from_json(ir_json)

    def test_float_max_iterations_rejected(self):
        """Float max_iterations raises ValueError on deserialization."""
        ir_json = json.dumps({
            "ir_version": "0.1",
            "entry": "a",
            "nodes": {
                "a": {
                    "capabilities_declared": [],
                    "capabilities_paged": [],
                    "edges": {"on_success": "a"},
                    "terminal": False,
                    "loop": {"max_iterations": 3.5},
                },
            },
        })
        with pytest.raises(ValueError, match="invalid max_iterations"):
            CompiledProgram.from_json(ir_json)

    def test_none_max_iterations_rejected(self):
        """None max_iterations raises ValueError on deserialization."""
        ir_json = json.dumps({
            "ir_version": "0.1",
            "entry": "a",
            "nodes": {
                "a": {
                    "capabilities_declared": [],
                    "capabilities_paged": [],
                    "edges": {"on_success": "a"},
                    "terminal": False,
                    "loop": {"max_iterations": None},
                },
            },
        })
        with pytest.raises(ValueError, match="invalid max_iterations"):
            CompiledProgram.from_json(ir_json)
