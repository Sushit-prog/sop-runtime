"""Integration tests: full parse of the example SOP."""

from pathlib import Path

import pytest

from sopvm.parser import SopDocument, parse

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "refund-request-handling.sop.yaml"


class TestRefundRequestHandling:
    @pytest.fixture(scope="class")
    def doc(self) -> SopDocument:
        return parse(FIXTURE)

    def test_version(self, doc):
        assert doc.version == "0.1"

    def test_policy_ref(self, doc):
        assert doc.policy_ref == "policies/support-agent.policy.yaml"

    def test_step_count(self, doc):
        assert len(doc.steps) == 5

    def test_first_step_id(self, doc):
        assert doc.steps[0].id == "verify_identity"

    def test_first_step_description(self, doc):
        assert "identity" in doc.steps[0].description.lower()

    def test_first_step_capabilities(self, doc):
        caps = [c.raw for c in doc.steps[0].requires]
        assert caps == ["db:read(orders)"]

    def test_first_step_edges(self, doc):
        assert doc.steps[0].edges == ("check_eligibility", "escalate_human")

    def test_first_step_not_terminal(self, doc):
        assert doc.steps[0].terminal is False

    def test_terminal_steps(self, doc):
        terminals = [s for s in doc.steps if s.terminal]
        assert len(terminals) == 2
        assert {s.id for s in terminals} == {"notify_user", "escalate_human"}

    def test_terminal_steps_have_no_edges(self, doc):
        for s in doc.steps:
            if s.terminal:
                assert s.edges == (None, None), f"terminal step {s.id} has edges"

    def test_step_ids_in_order(self, doc):
        ids = [s.id for s in doc.steps]
        assert ids == [
            "verify_identity",
            "check_eligibility",
            "issue_refund",
            "notify_user",
            "escalate_human",
        ]

    def test_issue_refund_capability(self, doc):
        step = next(s for s in doc.steps if s.id == "issue_refund")
        caps = [c.raw for c in step.requires]
        assert caps == ["payments:refund(max_amount=100.00)"]
