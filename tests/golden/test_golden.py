"""Golden-file tests: AST JSON snapshot comparison."""

import json
from pathlib import Path

import pytest

from sopvm.parser import SopDocument, parse

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "refund-request-handling.sop.yaml"
GOLDEN = Path(__file__).resolve().parents[1] / "golden" / "refund-request-handling.ast.json"


def _ast_to_dict(doc: SopDocument) -> dict:
    """Serialize SopDocument to a plain dict for JSON comparison."""
    return {
        "version": doc.version,
        "policy_ref": doc.policy_ref,
        "steps": [
            {
                "id": s.id,
                "description": s.description,
                "requires": [{"raw": c.raw} for c in s.requires],
                "edges": {"on_success": s.edges[0], "on_failure": s.edges[1]},
                "terminal": s.terminal,
            }
            for s in doc.steps
        ],
    }


class TestGoldenFile:
    def test_ast_matches_golden(self):
        doc = parse(FIXTURE)
        actual = _ast_to_dict(doc)
        expected = json.loads(GOLDEN.read_text(encoding="utf-8"))
        assert actual == expected

    def test_golden_update(self, request, recwarn):
        """Regenerate golden file when --update-golden is passed."""
        if not request.config.getoption("--update-golden", default=False):
            pytest.skip("pass --update-golden to regenerate")
        doc = parse(FIXTURE)
        GOLDEN.write_text(
            json.dumps(_ast_to_dict(doc), indent=2, sort_keys=False) + "\n",
            encoding="utf-8",
        )
