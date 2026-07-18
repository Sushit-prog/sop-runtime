"""Unit tests for the capability gate."""

from sopvm.capability.token import parse_capability
from sopvm.ir.model import IrNode
from sopvm.runtime.gate import CapabilityGate


class TestCheckCall:
    def test_allowed_cap_passes(self):
        node = IrNode(
            capabilities_declared=["db:read(orders)"],
            capabilities_paged=["db:read(orders)"],
        )
        gate = CapabilityGate()
        requested = parse_capability("db:read(orders)")
        assert gate.check_call("step1", requested, node) is True

    def test_disallowed_cap_fails(self):
        node = IrNode(
            capabilities_declared=["db:read(orders)"],
            capabilities_paged=["db:read(orders)"],
        )
        gate = CapabilityGate()
        requested = parse_capability("fs:write(/tmp)")
        assert gate.check_call("step1", requested, node) is False

    def test_ceiling_satisfied(self):
        node = IrNode(
            capabilities_declared=["payments:refund(max_amount=50.00)"],
            capabilities_paged=["payments:refund(max_amount<=100.00)"],
        )
        gate = CapabilityGate()
        requested = parse_capability("payments:refund(max_amount=50.00)")
        assert gate.check_call("step1", requested, node) is True

    def test_ceiling_exceeded(self):
        node = IrNode(
            capabilities_declared=["payments:refund(max_amount=250.00)"],
            capabilities_paged=["payments:refund(max_amount<=100.00)"],
        )
        gate = CapabilityGate()
        requested = parse_capability("payments:refund(max_amount=250.00)")
        assert gate.check_call("step1", requested, node) is False

    def test_empty_paged_always_fails(self):
        node = IrNode(
            capabilities_declared=["db:read(orders)"],
            capabilities_paged=[],
        )
        gate = CapabilityGate()
        requested = parse_capability("db:read(orders)")
        assert gate.check_call("step1", requested, node) is False


class TestEnforce:
    def test_allowed_returns_none(self):
        node = IrNode(
            capabilities_declared=["db:read(orders)"],
            capabilities_paged=["db:read(orders)"],
        )
        gate = CapabilityGate()
        requested = parse_capability("db:read(orders)")
        assert gate.enforce("step1", requested, node) is None

    def test_denied_returns_violation(self):
        node = IrNode(
            capabilities_declared=["db:read(orders)"],
            capabilities_paged=["db:read(orders)"],
        )
        gate = CapabilityGate()
        requested = parse_capability("fs:write(/tmp)")
        violation = gate.enforce("step1", requested, node)
        assert violation is not None
        assert violation.step_id == "step1"
        assert violation.requested.raw == "fs:write(/tmp)"
        assert "not satisfied" in violation.reason
