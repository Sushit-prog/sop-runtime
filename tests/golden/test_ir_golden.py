"""Golden-file test: IR JSON snapshot from the same source fixture as M2's AST."""

import json
from pathlib import Path

import pytest

from sopvm.compiler import lower
from sopvm.ir.model import CompiledProgram
from sopvm.parser import parse

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "refund-request-handling.sop.yaml"
GOLDEN = Path(__file__).resolve().parents[1] / "golden" / "refund-request-handling.ir.json"


def _ir_to_dict(prog: CompiledProgram) -> dict:
    """Serialize CompiledProgram to a plain dict for JSON comparison."""
    return {
        "ir_version": prog.ir_version,
        "entry": prog.entry,
        "nodes": {
            k: {
                "capabilities_declared": v.capabilities_declared,
                "capabilities_paged": v.capabilities_paged,
                "edges": v.edges,
                "terminal": v.terminal,
            }
            for k, v in prog.nodes.items()
        },
    }


class TestGoldenIR:
    def test_ir_matches_golden(self):
        doc = parse(FIXTURE)
        prog = lower(doc)
        actual = _ir_to_dict(prog)
        expected = json.loads(GOLDEN.read_text(encoding="utf-8"))
        assert actual == expected

    def test_golden_update(self, request):
        if not request.config.getoption("--update-golden", default=False):
            pytest.skip("pass --update-golden to regenerate")
        doc = parse(FIXTURE)
        prog = lower(doc)
        GOLDEN.write_text(
            json.dumps(_ir_to_dict(prog), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
