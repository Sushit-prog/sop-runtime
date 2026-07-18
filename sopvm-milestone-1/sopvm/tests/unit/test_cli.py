"""End-to-end tests for the `sopvm` CLI (Milestone 1: `compile --check` only).

These tests call `cli.main.main()` directly with an argv list rather
than shelling out via `subprocess`, so they run at unit-test speed
(no interpreter startup cost per test) while still exercising the
real argument parsing, file I/O, and error-formatting code paths.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cli.main import main

VALID_SOP = (
    "---\n"
    "id: cli-check\n"
    "version: 1\n"
    "owner: platform-team\n"
    "---\n"
    "# CLI Check SOP\n"
    "1. Do the thing.\n"
    "2. Confirm the thing was done.\n"
)

INVALID_SOP = "# No frontmatter\n1. Step.\n"


@pytest.fixture()
def valid_sop_file(tmp_path: Path) -> Path:
    path = tmp_path / "valid.md"
    path.write_text(VALID_SOP, encoding="utf-8")
    return path


@pytest.fixture()
def invalid_sop_file(tmp_path: Path) -> Path:
    path = tmp_path / "invalid.md"
    path.write_text(INVALID_SOP, encoding="utf-8")
    return path


def test_compile_check_success_prints_summary_and_returns_zero(
    valid_sop_file: Path, capsys: pytest.CaptureFixture[str]
):
    exit_code = main(["compile", "--check", str(valid_sop_file)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "valid SOP" in captured.out
    assert "id=cli-check" in captured.out
    assert "steps=2" in captured.out
    assert captured.err == ""


def test_compile_check_failure_reports_errors_and_returns_one(
    invalid_sop_file: Path, capsys: pytest.CaptureFixture[str]
):
    exit_code = main(["compile", "--check", str(invalid_sop_file)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "error(s)" in captured.err
    assert "frontmatter block" in captured.err
    assert captured.out == ""


def test_compile_without_check_flag_is_rejected_with_exit_code_two(
    valid_sop_file: Path, capsys: pytest.CaptureFixture[str]
):
    exit_code = main(["compile", str(valid_sop_file)])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "not implemented yet" in captured.err
    assert "Milestone 2" in captured.err


def test_compile_check_nonexistent_file_returns_two(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    missing = tmp_path / "does-not-exist.md"

    exit_code = main(["compile", "--check", str(missing)])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "no such file" in captured.err


def test_compile_check_on_a_directory_returns_two(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    exit_code = main(["compile", "--check", str(tmp_path)])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "not a file" in captured.err


def test_missing_subcommand_exits_via_argparse():
    with pytest.raises(SystemExit):
        main([])


def test_example_hello_sop_compiles_successfully(capsys: pytest.CaptureFixture[str]):
    # Regression/smoke test: the shipped example must always compile,
    # since it is what README.md tells new users to try first.
    example = Path(__file__).parents[2] / "examples" / "hello-sop" / "hello.md"

    exit_code = main(["compile", "--check", str(example)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "steps=3" in captured.out
