"""Unit tests for AST->IR lowering."""

import pytest

from sopvm.compiler import LoweringError, lower
from sopvm.ir.model import CompiledProgram, IrNode
from sopvm.parser.ast import CapabilityRequest, SopDocument, StepNode


def _step(sid: str, caps: list[str] | None = None, *, terminal: bool = False,
          on_success: str | None = None, on_failure: str | None = None) -> StepNode:
    reqs = tuple(CapabilityRequest(raw=c) for c in (caps or []))
    return StepNode(
        id=sid,
        description=None,
        requires=reqs,
        edges=(on_success, on_failure),
        terminal=terminal,
    )


class TestSingleStep:
    def test_single_terminal_step(self):
        doc = SopDocument(version="0.1", policy_ref="p", steps=(_step("done", ["db:read(x)"], terminal=True),))
        prog = lower(doc)
        assert prog.ir_version == "0.1"
        assert prog.entry == "done"
        assert len(prog.nodes) == 1
        node = prog.nodes["done"]
        assert node.terminal is True
        assert node.capabilities_declared == ["db:read(x)"]
        assert node.capabilities_paged == ["db:read(x)"]
        assert node.edges == {}

    def test_single_non_terminal_step(self):
        doc = SopDocument(version="0.1", policy_ref="p",
                          steps=(_step("a", ["cap:a"], on_success="b"),))
        # Cannot test edges target resolution here (that's M2's job),
        # but lowering should faithfully copy whatever edges exist.
        prog = lower(doc)
        assert prog.nodes["a"].edges == {"on_success": "b"}


class TestBranching:
    def test_step_with_both_edges(self):
        doc = SopDocument(version="0.1", policy_ref="p", steps=(
            _step("a", ["c1"], on_success="b", on_failure="c"),
            _step("b", terminal=True),
            _step("c", terminal=True),
        ))
        prog = lower(doc)
        assert prog.nodes["a"].edges == {"on_success": "b", "on_failure": "c"}

    def test_step_with_only_on_failure(self):
        doc = SopDocument(version="0.1", policy_ref="p", steps=(
            _step("a", on_failure="b"),
            _step("b", terminal=True),
        ))
        prog = lower(doc)
        assert prog.nodes["a"].edges == {"on_failure": "b"}


class TestMultipleCapabilities:
    def test_step_with_multiple_caps(self):
        doc = SopDocument(version="0.1", policy_ref="p", steps=(
            _step("a", ["db:read(x)", "db:read(y)", "net:http"], terminal=True),
        ))
        prog = lower(doc)
        node = prog.nodes["a"]
        assert node.capabilities_declared == ["db:read(x)", "db:read(y)", "net:http"]
        assert node.capabilities_paged == ["db:read(x)", "db:read(y)", "net:http"]


class TestCapabilitiesPagedEqualsDeclared:
    def test_paged_is_identical_copy(self):
        doc = SopDocument(version="0.1", policy_ref="p", steps=(
            _step("a", ["x", "y", "z"], terminal=True),
        ))
        prog = lower(doc)
        node = prog.nodes["a"]
        assert node.capabilities_paged == node.capabilities_declared
        # Verify it's an independent copy, not the same list object
        assert node.capabilities_paged is not node.capabilities_declared


class TestEntryNode:
    def test_entry_is_first_step(self):
        doc = SopDocument(version="0.1", policy_ref="p", steps=(
            _step("first", terminal=True),
        ))
        prog = lower(doc)
        assert prog.entry == "first"


class TestLoweringError:
    def test_empty_steps_raises(self):
        doc = SopDocument(version="0.1", policy_ref="p", steps=())
        with pytest.raises(LoweringError, match="empty"):
            lower(doc)


class TestJsonRoundTrip:
    def test_to_json_and_back(self):
        doc = SopDocument(version="0.1", policy_ref="p", steps=(
            _step("a", ["c1"], on_success="b"),
            _step("b", terminal=True),
        ))
        prog = lower(doc)
        json_str = prog.to_json()
        restored = CompiledProgram.from_json(json_str)
        assert restored == prog

    def test_deterministic_json_keys(self):
        doc = SopDocument(version="0.1", policy_ref="p", steps=(
            _step("b_step", terminal=True),
            _step("a_step", terminal=True),
        ))
        prog = lower(doc)
        json_str = prog.to_json()
        parsed = __import__("json").loads(json_str)
        # Top-level keys sorted
        assert list(parsed.keys()) == ["entry", "ir_version", "nodes"]
        # Node keys sorted within the nodes dict
        assert list(parsed["nodes"].keys()) == ["a_step", "b_step"]
