"""Unit tests for the paging pass (apply_paging)."""

from sopvm.capability.policy import Policy
from sopvm.capability.token import parse_capability
from sopvm.compiler.page import apply_paging
from sopvm.ir.model import CompiledProgram, IrNode


def _program(nodes: dict[str, list[str]]) -> CompiledProgram:
    """Build a minimal CompiledProgram from {step_id: [cap_strings]}."""
    ir_nodes = {}
    for sid, caps in nodes.items():
        ir_nodes[sid] = IrNode(
            capabilities_declared=list(caps),
            capabilities_paged=list(caps),  # will be overwritten
            edges={},
            terminal=True,
        )
    first = next(iter(nodes))
    return CompiledProgram(ir_version="0.1", entry=first, nodes=ir_nodes)


def _policy(*cap_strs: str) -> Policy:
    return Policy(
        policy_version="0.1",
        allowed_capabilities=tuple(parse_capability(c) for c in cap_strs),
    )


class TestNarrowing:
    def test_all_pass_through(self):
        prog = _program({"a": ["db:read(orders)", "notify:email"]})
        policy = _policy("db:read(orders)", "notify:email")
        result = apply_paging(prog, policy)
        assert result.nodes["a"].capabilities_paged == ["db:read(orders)", "notify:email"]

    def test_one_narrowed(self):
        prog = _program({"a": ["db:read(orders)", "fs:write(/tmp)"]})
        policy = _policy("db:read(orders)")
        result = apply_paging(prog, policy)
        assert result.nodes["a"].capabilities_paged == ["db:read(orders)"]

    def test_all_narrowed(self):
        prog = _program({"a": ["fs:write(/tmp)", "net:http"]})
        policy = _policy("db:read(orders)")
        result = apply_paging(prog, policy)
        assert result.nodes["a"].capabilities_paged == []

    def test_zero_capabilities_is_valid(self):
        """Zero capabilities_paged is a valid representable state."""
        prog = _program({"a": ["fs:write(/tmp)"]})
        policy = _policy("db:read(orders)")
        result = apply_paging(prog, policy)
        assert result.nodes["a"].capabilities_paged == []
        assert result.nodes["a"].terminal is True


class TestCeilingNarrowing:
    def test_ceiling_satisfied(self):
        prog = _program({"a": ["payments:refund(max_amount=50.00)"]})
        policy = _policy("payments:refund(max_amount<=100.00)")
        result = apply_paging(prog, policy)
        assert result.nodes["a"].capabilities_paged == ["payments:refund(max_amount=50.00)"]

    def test_ceiling_exceeded(self):
        prog = _program({"a": ["payments:refund(max_amount=250.00)"]})
        policy = _policy("payments:refund(max_amount<=100.00)")
        result = apply_paging(prog, policy)
        assert result.nodes["a"].capabilities_paged == []

    def test_ceiling_boundary(self):
        prog = _program({"a": ["payments:refund(max_amount=100.00)"]})
        policy = _policy("payments:refund(max_amount<=100.00)")
        result = apply_paging(prog, policy)
        assert result.nodes["a"].capabilities_paged == ["payments:refund(max_amount=100.00)"]


class TestMultipleNodes:
    def test_mixed_across_nodes(self):
        prog = _program({
            "a": ["db:read(orders)", "fs:write(/tmp)"],
            "b": ["notify:email"],
        })
        policy = _policy("db:read(orders)", "notify:email")
        result = apply_paging(prog, policy)
        assert result.nodes["a"].capabilities_paged == ["db:read(orders)"]
        assert result.nodes["b"].capabilities_paged == ["notify:email"]


class TestImmutability:
    def test_input_not_mutated(self):
        prog = _program({"a": ["db:read(orders)", "fs:write(/tmp)"]})
        original_paged = list(prog.nodes["a"].capabilities_paged)
        policy = _policy("db:read(orders)")
        apply_paging(prog, policy)
        assert prog.nodes["a"].capabilities_paged == original_paged

    def test_declared_unchanged(self):
        prog = _program({"a": ["db:read(orders)", "fs:write(/tmp)"]})
        policy = _policy("db:read(orders)")
        result = apply_paging(prog, policy)
        assert result.nodes["a"].capabilities_declared == ["db:read(orders)", "fs:write(/tmp)"]


class TestEdgesPreserved:
    def test_edges_copied(self):
        prog = _program({"a": ["db:read(orders)"]})
        prog.nodes["a"] = IrNode(
            capabilities_declared=["db:read(orders)"],
            capabilities_paged=["db:read(orders)"],
            edges={"on_success": "b", "on_failure": "c"},
            terminal=False,
        )
        policy = _policy("db:read(orders)")
        result = apply_paging(prog, policy)
        assert result.nodes["a"].edges == {"on_success": "b", "on_failure": "c"}


class TestIrVersionPreserved:
    def test_version_copied(self):
        prog = _program({"a": ["db:read(orders)"]})
        policy = _policy("db:read(orders)")
        result = apply_paging(prog, policy)
        assert result.ir_version == "0.1"
