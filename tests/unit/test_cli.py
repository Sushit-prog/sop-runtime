"""CLI tests via click.testing.CliRunner (Milestone 11)."""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from sopvm.cli.main import main

FIXTURE_SOP = Path(__file__).resolve().parents[1] / "fixtures" / "refund-request-handling.sop.yaml"
FIXTURE_POLICY = Path(__file__).resolve().parents[1].parent / "policies" / "support-agent.policy.yaml"


@pytest.fixture
def runner():
    return CliRunner()


class TestCompileCommand:
    def test_compile_success(self, runner, tmp_path):
        out = tmp_path / "out.ir.json"
        result = runner.invoke(main, [
            "compile", str(FIXTURE_SOP),
            "--policy", str(FIXTURE_POLICY),
            "-o", str(out),
        ])
        assert result.exit_code == 0
        assert out.exists()
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["ir_version"] == "0.1"
        assert data["entry"] == "verify_identity"

    def test_compile_bad_yaml_exit_2(self, runner, tmp_path):
        bad_sop = tmp_path / "bad.sop.yaml"
        bad_sop.write_text("not: valid: yaml: [[[\n", encoding="utf-8")
        out = tmp_path / "out.ir.json"
        result = runner.invoke(main, [
            "compile", str(bad_sop),
            "--policy", str(FIXTURE_POLICY),
            "-o", str(out),
        ])
        assert result.exit_code == 2
        assert "Error" in result.output or "error" in result.stderr

    def test_compile_missing_sop(self, runner):
        result = runner.invoke(main, [
            "compile", "nonexistent.yaml",
            "--policy", str(FIXTURE_POLICY),
            "-o", "out.json",
        ])
        assert result.exit_code != 0

    def test_compile_no_traceback(self, runner, tmp_path):
        bad_sop = tmp_path / "bad.sop.yaml"
        bad_sop.write_text("sop_version: 1\n", encoding="utf-8")
        out = tmp_path / "out.ir.json"
        result = runner.invoke(main, [
            "compile", str(bad_sop),
            "--policy", str(FIXTURE_POLICY),
            "-o", str(out),
        ])
        assert "Traceback" not in result.output
        assert "Traceback" not in (result.stderr or "")


class TestCheckCommand:
    def test_check_pass(self, runner, tmp_path):
        # First compile
        ir = tmp_path / "test.ir.json"
        runner.invoke(main, [
            "compile", str(FIXTURE_SOP),
            "--policy", str(FIXTURE_POLICY),
            "-o", str(ir),
        ])
        # Then check
        result = runner.invoke(main, [
            "check", str(ir),
            "--policy", str(FIXTURE_POLICY),
        ])
        assert result.exit_code == 0
        assert "All capabilities within policy" in (result.stderr or result.output)

    def test_check_violation_exit_1(self, runner, tmp_path):
        # Create an IR with a violating capability
        ir_data = {
            "ir_version": "0.1",
            "entry": "a",
            "nodes": {
                "a": {
                    "capabilities_declared": ["payments:refund(max_amount=250.00)"],
                    "capabilities_paged": ["payments:refund(max_amount=250.00)"],
                    "edges": {},
                    "terminal": True,
                },
            },
        }
        ir = tmp_path / "violating.ir.json"
        ir.write_text(json.dumps(ir_data), encoding="utf-8")
        result = runner.invoke(main, [
            "check", str(ir),
            "--policy", str(FIXTURE_POLICY),
        ])
        assert result.exit_code == 1
        assert "VIOLATION" in (result.stderr or result.output)


class TestTraceCommand:
    def test_trace_shows_events(self, runner, tmp_path):
        # Create a JSONL log with known events
        log = tmp_path / "trace.jsonl"
        events = [
            {"event": "run_started", "step_id": "", "timestamp": "2026-01-01T00:00:00Z", "run_id": "r1"},
            {"event": "step_started", "step_id": "a", "timestamp": "2026-01-01T00:00:01Z", "run_id": "r1"},
            {"event": "step_completed", "step_id": "a", "timestamp": "2026-01-01T00:00:02Z", "run_id": "r1"},
            {"event": "run_completed", "step_id": "", "timestamp": "2026-01-01T00:00:03Z", "run_id": "r1"},
            {"event": "run_started", "step_id": "", "timestamp": "2026-01-02T00:00:00Z", "run_id": "r2"},
        ]
        with open(log, "w", encoding="utf-8") as f:
            for e in events:
                f.write(json.dumps(e) + "\n")

        result = runner.invoke(main, ["trace", str(log), "r1"])
        assert result.exit_code == 0
        assert "run_started" in result.output
        assert "step_started" in result.output
        assert "step_completed" in result.output
        # r2 events should not appear
        assert "2026-01-02" not in result.output

    def test_trace_missing_run_id_exit_1(self, runner, tmp_path):
        log = tmp_path / "trace.jsonl"
        log.write_text('{"event":"run_started","step_id":"","timestamp":"t","run_id":"other"}\n',
                        encoding="utf-8")
        result = runner.invoke(main, ["trace", str(log), "nonexistent"])
        assert result.exit_code == 1
        assert "No events found" in (result.stderr or result.output)
