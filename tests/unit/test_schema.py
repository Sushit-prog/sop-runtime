"""Schema validation edge-case tests."""

from pathlib import Path

import pytest

from sopvm.parser import SchemaValidationError, parse

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _write_yaml(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "test.sop.yaml"
    p.write_text(content, encoding="utf-8")
    return p


class TestRequiredFields:
    def test_missing_sop_version(self, tmp_path):
        p = _write_yaml(tmp_path, 'name: "x"\npolicy: "p"\nsteps:\n  - id: a\n    description: d\n    requires:\n      capabilities: ["db:read(x)"]')
        with pytest.raises(SchemaValidationError, match="sop_version"):
            parse(p)

    def test_missing_name(self, tmp_path):
        p = _write_yaml(tmp_path, 'sop_version: "0.1"\npolicy: "p"\nsteps:\n  - id: a\n    description: d\n    requires:\n      capabilities: ["db:read(x)"]')
        with pytest.raises(SchemaValidationError, match="name"):
            parse(p)

    def test_missing_policy(self, tmp_path):
        p = _write_yaml(tmp_path, 'sop_version: "0.1"\nname: "x"\nsteps:\n  - id: a\n    description: d\n    requires:\n      capabilities: ["db:read(x)"]')
        with pytest.raises(SchemaValidationError, match="policy"):
            parse(p)

    def test_missing_steps(self, tmp_path):
        p = _write_yaml(tmp_path, 'sop_version: "0.1"\nname: "x"\npolicy: "p"')
        with pytest.raises(SchemaValidationError, match="steps"):
            parse(p)


class TestStepsValidation:
    def test_empty_steps_list(self, tmp_path):
        p = _write_yaml(tmp_path, 'sop_version: "0.1"\nname: "x"\npolicy: "p"\nsteps: []')
        with pytest.raises(SchemaValidationError):
            parse(p)

    def test_step_missing_id(self, tmp_path):
        p = _write_yaml(tmp_path, 'sop_version: "0.1"\nname: "x"\npolicy: "p"\nsteps:\n  - description: d\n    requires:\n      capabilities: ["db:read(x)"]')
        with pytest.raises(SchemaValidationError):
            parse(p)

    def test_step_without_description_parses(self, tmp_path):
        p = _write_yaml(tmp_path, 'sop_version: "0.1"\nname: "x"\npolicy: "p"\nsteps:\n  - id: a\n    terminal: true\n    requires:\n      capabilities: ["db:read(x)"]')
        doc = parse(p)
        assert doc.steps[0].description is None

    def test_step_missing_requires(self, tmp_path):
        p = _write_yaml(tmp_path, 'sop_version: "0.1"\nname: "x"\npolicy: "p"\nsteps:\n  - id: a\n    description: d')
        with pytest.raises(SchemaValidationError):
            parse(p)

    def test_step_unknown_property_rejected(self, tmp_path):
        p = _write_yaml(tmp_path, 'sop_version: "0.1"\nname: "x"\npolicy: "p"\nsteps:\n  - id: a\n    description: d\n    requires:\n      capabilities: ["db:read(x)"]\n    foo: bar')
        with pytest.raises(SchemaValidationError):
            parse(p)

    def test_step_invalid_id_pattern(self, tmp_path):
        p = _write_yaml(tmp_path, 'sop_version: "0.1"\nname: "x"\npolicy: "p"\nsteps:\n  - id: "123-starts-with-number"\n    description: d\n    requires:\n      capabilities: ["db:read(x)"]')
        with pytest.raises(SchemaValidationError):
            parse(p)


class TestValidMinimalSOP:
    def test_single_terminal_step(self, tmp_path):
        p = _write_yaml(tmp_path, 'sop_version: "0.1"\nname: "x"\npolicy: "p"\nsteps:\n  - id: done\n    description: "All done"\n    terminal: true\n    requires:\n      capabilities: ["db:read(x)"]')
        doc = parse(p)
        assert doc.version == "0.1"
        assert doc.policy_ref == "p"
        assert len(doc.steps) == 1
        assert doc.steps[0].id == "done"
        assert doc.steps[0].terminal is True

    def test_valid_full_sop(self):
        doc = parse(FIXTURES / "refund-request-handling.sop.yaml")
        assert doc.version == "0.1"
        assert len(doc.steps) == 5
