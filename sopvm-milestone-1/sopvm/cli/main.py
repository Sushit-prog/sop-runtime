"""SOPVM command-line interface.

Milestone 1 ships a single, fully working subcommand:

    sopvm compile --check <file>

Running `sopvm compile` *without* `--check` is intentionally rejected
with a clear, actionable message rather than silently doing nothing or
crashing — non-`--check` compilation emits a `.sopc` executable
artifact via IR lowering and codegen, neither of which exist yet
(Milestone 2). Failing loudly and specifically here is preferable to
either a confusing no-op or a bare stack trace.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sopvm.api import compile_check
from sopvm.compiler.errors import SOPParseErrors


def _cmd_compile(args: argparse.Namespace) -> int:
    if not args.check:
        print(
            "error: `sopvm compile` without --check is not implemented yet.\n"
            "Milestone 1 only supports validation: `sopvm compile --check <file>`.\n"
            "Executable (.sopc) generation is planned for Milestone 2.",
            file=sys.stderr,
        )
        return 2

    path = Path(args.file)
    if not path.exists():
        print(f"error: no such file: {path}", file=sys.stderr)
        return 2
    if not path.is_file():
        print(f"error: not a file: {path}", file=sys.stderr)
        return 2

    try:
        procedure = compile_check(path)
    except SOPParseErrors as exc:
        print(f"\u2717 {path}: {len(exc.errors)} error(s)", file=sys.stderr)
        for err in exc.errors:
            print(f"  {err}", file=sys.stderr)
        return 1
    except UnicodeDecodeError as exc:
        print(f"error: {path} is not valid UTF-8 text: {exc}", file=sys.stderr)
        return 2

    print(f"\u2713 {path}: valid SOP")
    print(f"  id={procedure.id} version={procedure.version} owner={procedure.owner}")
    print(f"  title={procedure.title!r}")
    print(f"  steps={len(procedure.steps)}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sopvm",
        description="SOPVM: compile and (eventually) run Standard Operating Procedures.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    compile_parser = subparsers.add_parser(
        "compile", help="Compile (or, in this milestone, validate) a SOP source file."
    )
    compile_parser.add_argument("file", help="Path to the SOP Markdown source file.")
    compile_parser.add_argument(
        "--check",
        action="store_true",
        help=(
            "Validate the SOP without emitting an executable artifact. "
            "The only supported mode in this milestone."
        ),
    )
    compile_parser.set_defaults(func=_cmd_compile)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
