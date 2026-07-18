"""Integration test: LangGraph-wrapped vs direct executor equivalence.

Asserts that running the SOP through as_langgraph_node() and through
a direct Executor.run() on the same CompiledProgram produce equivalent
RunResults (same final state, same path).
"""

from pathlib import Path

import pytest

from sopvm.compiler.pipeline import compile_sop
from sopvm.integrations.langgraph.node import as_langgraph_node
from sopvm.runtime.executor import Executor, RunResult
from sopvm.runtime.state import StepState

FIXTURE_SOP = Path(__file__).resolve().parents[1] / "fixtures" / "refund-request-handling.sop.yaml"
FIXTURE_POLICY = Path(__file__).resolve().parents[1].parent / "policies" / "support-agent.policy.yaml"


class _DirectHandler:
    """Minimal handler for direct executor run — always succeeds."""
    def execute(self, node, request_tool=None) -> StepState:
        return StepState.DONE


class TestLangGraphEquivalence:
    @pytest.fixture(scope="class")
    def compiled(self):
        return compile_sop(str(FIXTURE_SOP), str(FIXTURE_POLICY))

    @pytest.fixture(scope="class")
    def direct_result(self, compiled) -> RunResult:
        return Executor(compiled, _DirectHandler()).run()

    @pytest.fixture(scope="class")
    def langgraph_result(self, compiled) -> dict:
        node_fn = as_langgraph_node(compiled)
        return node_fn({})

    def test_same_final_state(self, direct_result, langgraph_result):
        assert langgraph_result["sopvm_result"] == direct_result.final_state.value

    def test_same_path(self, direct_result, langgraph_result):
        assert langgraph_result["sopvm_path"] == list(direct_result.path)

    def test_path_starts_at_entry(self, direct_result):
        assert direct_result.path[0] == "verify_identity"

    def test_path_ends_at_terminal(self, direct_result):
        assert direct_result.path[-1] in ("notify_user", "escalate_human")

    def test_result_is_done(self, direct_result):
        assert direct_result.final_state == StepState.DONE
