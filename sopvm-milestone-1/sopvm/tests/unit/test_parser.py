"""Unit tests for `sopvm.compiler.parser.parse`.

Covers: happy path, every frontmatter validation rule, title
validation, step-sequencing validation, multi-line step text, and a
couple of regression cases for grammar edge cases that are easy to
get wrong in a line-oriented parser (e.g. "1)" vs "1.", stray content
between steps, CRLF-free assumptions).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sopvm.compiler.ast import Procedure, Step
from sopvm.compiler.errors import SOPParseErrors
from sopvm.compiler.parser import parse

FIXTURES = Path(__file__).parent / "fixtures"


# --- Happy path --------------------------------------------------------


def test_valid_minimal_procedure_parses():
    source = (
        "---\n"
        "id: onboard-new-hire\n"
        "version: 1\n"
        "owner: people-ops\n"
        "---\n"
        "# Onboard a New Hire\n"
        "\n"
        "1. Create the accounts.\n"
        "2. Send the welcome email.\n"
        "3. Schedule the first-week check-in.\n"
    )

    procedure = parse(source, source_path="inline")

    assert isinstance(procedure, Procedure)
    assert procedure.id == "onboard-new-hire"
    assert procedure.version == 1
    assert procedure.owner == "people-ops"
    assert procedure.title == "Onboard a New Hire"
    assert procedure.source_path == "inline"
    assert procedure.steps == (
        Step(index=1, text="Create the accounts.", source_line=8),
        Step(index=2, text="Send the welcome email.", source_line=9),
        Step(index=3, text="Schedule the first-week check-in.", source_line=10),
    )


def test_multiline_step_text_is_captured_and_joined():
    source = (
        "---\n"
        "id: multi\n"
        "version: 1\n"
        "owner: team\n"
        "---\n"
        "# Multi-line Steps\n"
        "1. Do the first thing,\n"
        "   which spans two lines.\n"
        "2. Do the second thing.\n"
    )

    procedure = parse(source)

    assert procedure.steps[0].text == "Do the first thing,\nwhich spans two lines."
    assert procedure.steps[1].text == "Do the second thing."


def test_blank_lines_between_steps_are_tolerated():
    source = (
        "---\n"
        "id: spaced\n"
        "version: 1\n"
        "owner: team\n"
        "---\n"
        "# Spaced Steps\n"
        "\n"
        "1. First.\n"
        "\n"
        "\n"
        "2. Second.\n"
    )

    procedure = parse(source)

    assert [s.index for s in procedure.steps] == [1, 2]


def test_real_fixture_file_parses_via_pathlib(tmp_path=None):
    text = (FIXTURES / "valid.md").read_text(encoding="utf-8")
    procedure = parse(text, source_path=str(FIXTURES / "valid.md"))
    assert procedure.id == "fixture-valid"
    assert len(procedure.steps) == 3
    assert procedure.steps[1].text == (
        "Do the second thing,\nwhich continues onto a second line."
    )


# --- Frontmatter structural errors --------------------------------------


def test_missing_frontmatter_block_raises_single_error():
    source = "# No Frontmatter\n1. Step one.\n"

    with pytest.raises(SOPParseErrors) as exc_info:
        parse(source)

    assert len(exc_info.value.errors) == 1
    assert "must start with a YAML frontmatter block" in str(exc_info.value.errors[0])
    assert exc_info.value.errors[0].line == 1


def test_missing_frontmatter_fixture_file_raises():
    text = (FIXTURES / "missing_frontmatter.md").read_text(encoding="utf-8")
    with pytest.raises(SOPParseErrors):
        parse(text)


def test_unterminated_frontmatter_raises_single_error():
    source = "---\nid: x\nversion: 1\nowner: team\n# Title\n1. Step.\n"

    with pytest.raises(SOPParseErrors) as exc_info:
        parse(source)

    assert len(exc_info.value.errors) == 1
    assert "unterminated frontmatter" in str(exc_info.value.errors[0])


def test_invalid_yaml_frontmatter_raises_and_still_reports_body_errors():
    # Invalid YAML (bad indentation) *and* no title/steps afterwards --
    # the parser should report both, proving it recovers past the YAML
    # error to keep validating the rest of the document.
    source = "---\nid: x\n  version: [1\nowner: team\n---\n"

    with pytest.raises(SOPParseErrors) as exc_info:
        parse(source)

    messages = [str(e) for e in exc_info.value.errors]
    assert any("invalid YAML in frontmatter" in m for m in messages)
    assert any("missing title heading" in m for m in messages)


# --- Frontmatter field validation ---------------------------------------


def test_missing_required_fields_are_all_reported_together():
    source = "---\nid: only-id\n---\n# Title\n1. Step.\n"

    with pytest.raises(SOPParseErrors) as exc_info:
        parse(source)

    messages = [str(e) for e in exc_info.value.errors]
    assert any("'version'" in m for m in messages)
    assert any("'owner'" in m for m in messages)
    assert not any("'id'" in m for m in messages)


def test_typo_in_frontmatter_key_suggests_correct_name():
    source = "---\nid: x\nversion: 1\nonwer: team\n---\n# Title\n1. Step.\n"

    with pytest.raises(SOPParseErrors) as exc_info:
        parse(source)

    owner_errors = [e for e in exc_info.value.errors if "owner" in e.message]
    assert owner_errors, "expected a missing 'owner' error"
    assert owner_errors[0].suggestion == "onwer"


def test_non_string_id_is_rejected():
    source = "---\nid: 123\nversion: 1\nowner: team\n---\n# Title\n1. Step.\n"

    with pytest.raises(SOPParseErrors) as exc_info:
        parse(source)

    assert any("'id' must be a non-empty string" in str(e) for e in exc_info.value.errors)


def test_empty_owner_string_is_rejected():
    source = '---\nid: x\nversion: 1\nowner: ""\n---\n# Title\n1. Step.\n'

    with pytest.raises(SOPParseErrors) as exc_info:
        parse(source)

    assert any("'owner' must be a non-empty string" in str(e) for e in exc_info.value.errors)


def test_non_integer_version_is_rejected():
    source = "---\nid: x\nversion: \"1.0\"\nowner: team\n---\n# Title\n1. Step.\n"

    with pytest.raises(SOPParseErrors) as exc_info:
        parse(source)

    assert any("'version' must be an integer" in str(e) for e in exc_info.value.errors)


def test_boolean_version_is_rejected():
    # Regression test: bool is a subclass of int in Python, so a naive
    # `isinstance(v, int)` check would silently accept `version: true`.
    source = "---\nid: x\nversion: true\nowner: team\n---\n# Title\n1. Step.\n"

    with pytest.raises(SOPParseErrors) as exc_info:
        parse(source)

    assert any("'version' must be an integer" in str(e) for e in exc_info.value.errors)


# --- Title validation -----------------------------------------------------


def test_missing_title_is_reported():
    source = "---\nid: x\nversion: 1\nowner: team\n---\n1. Step without a title.\n"

    with pytest.raises(SOPParseErrors) as exc_info:
        parse(source)

    assert any("title heading" in str(e) for e in exc_info.value.errors)


def test_empty_title_is_rejected():
    source = "---\nid: x\nversion: 1\nowner: team\n---\n# \n1. Step.\n"

    with pytest.raises(SOPParseErrors) as exc_info:
        parse(source)

    assert any("title heading must not be empty" in str(e) for e in exc_info.value.errors)


# --- Step sequencing validation --------------------------------------------


def test_no_steps_found_is_reported():
    source = "---\nid: x\nversion: 1\nowner: team\n---\n# Title\n"

    with pytest.raises(SOPParseErrors) as exc_info:
        parse(source)

    assert any("no steps found" in str(e) for e in exc_info.value.errors)


def test_steps_not_starting_at_one_is_rejected():
    source = "---\nid: x\nversion: 1\nowner: team\n---\n# Title\n2. Starts at two.\n"

    with pytest.raises(SOPParseErrors) as exc_info:
        parse(source)

    assert any("expected step 1, found step 2" in str(e) for e in exc_info.value.errors)


def test_gap_in_step_numbering_is_rejected():
    source = (
        "---\nid: x\nversion: 1\nowner: team\n---\n# Title\n"
        "1. First.\n3. Skips two.\n"
    )

    with pytest.raises(SOPParseErrors) as exc_info:
        parse(source)

    assert any("expected step 2, found step 3" in str(e) for e in exc_info.value.errors)


def test_duplicate_step_number_is_rejected():
    source = (
        "---\nid: x\nversion: 1\nowner: team\n---\n# Title\n"
        "1. First.\n1. First again.\n2. Second.\n"
    )

    with pytest.raises(SOPParseErrors) as exc_info:
        parse(source)

    assert any("duplicate step number 1" in str(e) for e in exc_info.value.errors)


def test_recovers_after_a_numbering_gap_and_does_not_cascade_errors():
    # A single gap (step 3 instead of 2) should produce exactly one
    # sequencing error, not one per subsequent step.
    source = (
        "---\nid: x\nversion: 1\nowner: team\n---\n# Title\n"
        "1. First.\n3. Skips two.\n4. Continues normally.\n"
    )

    with pytest.raises(SOPParseErrors) as exc_info:
        parse(source)

    sequencing_errors = [
        e for e in exc_info.value.errors if "expected step" in str(e)
    ]
    assert len(sequencing_errors) == 1


def test_parenthesis_style_numbering_is_not_recognized_as_a_step():
    # Regression test: only "N. " is valid step syntax in this
    # milestone; "N)" must not be silently accepted as equivalent.
    source = "---\nid: x\nversion: 1\nowner: team\n---\n# Title\n1) Wrong syntax.\n"

    with pytest.raises(SOPParseErrors) as exc_info:
        parse(source)

    messages = [str(e) for e in exc_info.value.errors]
    assert any("unexpected content outside of a numbered step" in m for m in messages)
    assert any("no steps found" in m for m in messages)


def test_content_before_first_step_is_rejected():
    source = (
        "---\nid: x\nversion: 1\nowner: team\n---\n# Title\n"
        "Some stray paragraph before any numbered step.\n"
        "1. First real step.\n"
    )

    with pytest.raises(SOPParseErrors) as exc_info:
        parse(source)

    assert any(
        "unexpected content outside of a numbered step" in str(e)
        for e in exc_info.value.errors
    )


# --- Batch error collection -------------------------------------------------


def test_multiple_unrelated_errors_are_all_collected_in_one_pass():
    # Missing frontmatter field + missing title + zero steps, all in a
    # single document, should all surface in a single SOPParseErrors.
    source = "---\nid: x\nowner: team\n---\n"

    with pytest.raises(SOPParseErrors) as exc_info:
        parse(source)

    messages = [str(e) for e in exc_info.value.errors]
    assert any("'version'" in m for m in messages)
    assert any("missing title heading" in m for m in messages)
    assert len(exc_info.value.errors) >= 2
