"""Unit tests for the static capability checker."""

import pytest

from sopvm.capability.token import parse_capability
from sopvm.capability.policy import Policy
from sopvm.checker.check import CheckResult, Violation, check, satisfies


class TestSatisfies:
    def test_exact_match_no_params(self):
        req = parse_capability("notify:email")
        allowed = parse_capability("notify:email")
        assert satisfies(req, allowed) is True

    def test_namespace_mismatch(self):
        req = parse_capability("fs:read(x)")
        allowed = parse_capability("db:read(x)")
        assert satisfies(req, allowed) is False

    def test_action_mismatch(self):
        req = parse_capability("db:write(x)")
        allowed = parse_capability("db:read(x)")
        assert satisfies(req, allowed) is False

    def test_exact_param_match(self):
        req = parse_capability("db:read(orders)")
        allowed = parse_capability("db:read(orders)")
        assert satisfies(req, allowed) is True

    def test_exact_param_mismatch(self):
        req = parse_capability("db:read(users)")
        allowed = parse_capability("db:read(orders)")
        assert satisfies(req, allowed) is False

    def test_ceiling_satisfied(self):
        req = parse_capability("payments:refund(max_amount=50.00)")
        allowed = parse_capability("payments:refund(max_amount<=100.00)")
        assert satisfies(req, allowed) is True

    def test_ceiling_exceeded(self):
        req = parse_capability("payments:refund(max_amount=250.00)")
        allowed = parse_capability("payments:refund(max_amount<=100.00)")
        assert satisfies(req, allowed) is False

    def test_ceiling_exact_boundary(self):
        req = parse_capability("payments:refund(max_amount=100.00)")
        allowed = parse_capability("payments:refund(max_amount<=100.00)")
        assert satisfies(req, allowed) is True

    def test_unconstrained_param_in_request(self):
        """Params in request not mentioned in allowed are unconstrained."""
        req = parse_capability("db:read(orders, extra=true)")
        allowed = parse_capability("db:read(orders)")
        assert satisfies(req, allowed) is True

    def test_unconstrained_param_in_policy(self):
        """Params in allowed without comparator must match exactly."""
        req = parse_capability("db:read(users)")
        allowed = parse_capability("db:read(orders)")
        assert satisfies(req, allowed) is False

    def test_ge_ceiling(self):
        req = parse_capability("db:read(min_version=5)")
        allowed = parse_capability("db:read(min_version>=3)")
        assert satisfies(req, allowed) is True

    def test_ge_ceiling_violated(self):
        req = parse_capability("db:read(min_version=1)")
        allowed = parse_capability("db:read(min_version>=3)")
        assert satisfies(req, allowed) is False

    def test_string_channel_match(self):
        req = parse_capability("notify:slack(channel=support-escalations)")
        allowed = parse_capability("notify:slack(channel=support-escalations)")
        assert satisfies(req, allowed) is True


class TestCheck:
    def _make_program(self, nodes: dict):
        from sopvm.ir.model import CompiledProgram, IrNode
        ir_nodes = {}
        for sid, caps in nodes.items():
            ir_nodes[sid] = IrNode(
                capabilities_declared=caps,
                capabilities_paged=list(caps),
                edges={},
                terminal=True,
            )
        first_id = next(iter(nodes))
        return CompiledProgram(ir_version="0.1", entry=first_id, nodes=ir_nodes)

    def test_all_pass(self):
        prog = self._make_program({"a": ["db:read(orders)"]})
        policy = Policy(
            policy_version="0.1",
            allowed_capabilities=(parse_capability("db:read(orders)"),),
        )
        result = check(prog, policy)
        assert result.passed is True
        assert result.violations == ()

    def test_violation_recorded(self):
        prog = self._make_program({"a": ["payments:refund(max_amount=250.00)"]})
        policy = Policy(
            policy_version="0.1",
            allowed_capabilities=(parse_capability("payments:refund(max_amount<=100.00)"),),
        )
        result = check(prog, policy)
        assert result.passed is False
        assert len(result.violations) == 1
        v = result.violations[0]
        assert v.step_id == "a"
        assert v.requested == "payments:refund(max_amount=250.00)"
        assert "exceeds" in v.reason

    def test_unmentioned_capability_violation(self):
        prog = self._make_program({"a": ["fs:write(/tmp)"]})
        policy = Policy(
            policy_version="0.1",
            allowed_capabilities=(parse_capability("db:read(x)"),),
        )
        result = check(prog, policy)
        assert result.passed is False
        assert "not mentioned" in result.violations[0].reason

    def test_multiple_steps_multiple_caps(self):
        prog = self._make_program({
            "a": ["db:read(orders)", "notify:email"],
            "b": ["payments:refund(max_amount=250.00)"],
        })
        policy = Policy(
            policy_version="0.1",
            allowed_capabilities=(
                parse_capability("db:read(orders)"),
                parse_capability("notify:email"),
                parse_capability("payments:refund(max_amount<=100.00)"),
            ),
        )
        result = check(prog, policy)
        assert result.passed is False
        assert len(result.violations) == 1
        assert result.violations[0].step_id == "b"
