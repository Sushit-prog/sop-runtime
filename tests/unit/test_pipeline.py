"""Unit tests for the compile pipeline."""

from pathlib import Path


from sopvm.compiler.pipeline import compile_sop

FIXTURE_SOP = Path(__file__).resolve().parents[1] / "fixtures" / "refund-request-handling.sop.yaml"
FIXTURE_POLICY = Path(__file__).resolve().parents[1].parent / "policies" / "support-agent.policy.yaml"


class TestCompileSop:
    def test_full_pipeline(self):
        prog = compile_sop(str(FIXTURE_SOP), str(FIXTURE_POLICY))
        assert prog.ir_version == "0.1"
        assert prog.entry == "verify_identity"
        assert len(prog.nodes) == 5

    def test_paging_applied(self):
        prog = compile_sop(str(FIXTURE_SOP), str(FIXTURE_POLICY))
        # All capabilities in the example SOP satisfy the policy
        for node in prog.nodes.values():
            assert node.capabilities_paged == node.capabilities_declared

    def test_entry_step(self):
        prog = compile_sop(str(FIXTURE_SOP), str(FIXTURE_POLICY))
        assert prog.entry == "verify_identity"
        node = prog.nodes["verify_identity"]
        assert node.terminal is False
        assert "db:read(orders)" in node.capabilities_paged

    def test_terminal_steps(self):
        prog = compile_sop(str(FIXTURE_SOP), str(FIXTURE_POLICY))
        for sid in ("notify_user", "escalate_human"):
            assert prog.nodes[sid].terminal is True
            assert prog.nodes[sid].edges == {}
