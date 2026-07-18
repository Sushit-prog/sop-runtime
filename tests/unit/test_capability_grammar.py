"""Capability grammar surface-pattern tests."""

import pytest

from sopvm.parser import SemanticError, parse
from pathlib import Path

from sopvm.parser.parse import _CAPABILITY_RE

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


class TestCapabilityRegex:
    """Direct regex matching tests (no file I/O)."""

    @pytest.mark.parametrize(
        "cap_str",
        [
            "db:read(orders)",
            "payments:refund(max_amount=100.00)",
            "notify:email",
            "fs:write(/tmp/out)",
            "a:b",
            "My_Namespace:My_Action(param1=val1, param2=val2)",
        ],
    )
    def test_valid_capability_strings(self, cap_str):
        assert _CAPABILITY_RE.match(cap_str), f"expected match for: {cap_str!r}"

    @pytest.mark.parametrize(
        "cap_str",
        [
            ":read(orders)",       # missing namespace
            "db:",                 # missing action
            "dbread(orders)",     # missing colon
            "db:read(orders",     # unmatched paren
            "db:read)orders(",    # wrong paren order
            "",                   # empty string
            "db read(orders)",    # space instead of colon
        ],
    )
    def test_invalid_capability_strings(self, cap_str):
        assert not _CAPABILITY_RE.match(cap_str), f"expected no match for: {cap_str!r}"


class TestCapabilityInParse:
    """Semantic error raised for malformed capability strings in parsed SOP."""

    def _write_yaml(self, tmp_path, caps_str: str) -> Path:
        p = tmp_path / "test.sop.yaml"
        p.write_text(
            f'sop_version: "0.1"\nname: "x"\npolicy: "p"\nsteps:\n'
            f'  - id: a\n    description: d\n    terminal: true\n'
            f'    requires:\n      capabilities: ["{caps_str}"]\n',
            encoding="utf-8",
        )
        return p

    def test_malformed_capability_raises_semantic_error(self, tmp_path):
        p = self._write_yaml(tmp_path, ":read(x)")
        with pytest.raises(SemanticError, match="malformed capability"):
            parse(p)

    def test_valid_capability_parses(self, tmp_path):
        p = self._write_yaml(tmp_path, "db:read(orders)")
        doc = parse(p)
        assert doc.steps[0].requires[0].raw == "db:read(orders)"
