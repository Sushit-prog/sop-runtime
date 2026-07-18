"""Integration test: full check pipeline on the example SOP + policy."""

from pathlib import Path

import pytest

from sopvm.capability.policy import load_policy
from sopvm.checker.check import check
from sopvm.compiler import lower
from sopvm.parser import parse

FIXTURE_SOP = Path(__file__).resolve().parents[1] / "fixtures" / "refund-request-handling.sop.yaml"
FIXTURE_POLICY = Path(__file__).resolve().parents[1].parent / "policies" / "support-agent.policy.yaml"


class TestFullPipeline:
    @pytest.fixture(scope="class")
    def result(self):
        doc = parse(FIXTURE_SOP)
        prog = lower(doc)
        policy = load_policy(FIXTURE_POLICY)
        return check(prog, policy)

    def test_check_passes(self, result):
        assert result.passed is True

    def test_no_violations(self, result):
        assert result.violations == ()

    def test_policy_has_five_entries(self):
        policy = load_policy(FIXTURE_POLICY)
        assert len(policy.allowed_capabilities) == 5
