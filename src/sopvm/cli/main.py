"""SOPVM CLI (Milestone 11).

Per INTERFACES.md §9:

    sopvm compile <sop.yaml> --policy <policy.yaml> -o <out.ir.json>
    sopvm check <out.ir.json> --policy <policy.yaml>
    sopvm run <out.ir.json> --providers <providers.yaml>
    sopvm trace <run_id>
"""

from __future__ import annotations

import json
import sys

import click
import yaml

from sopvm.capability.policy import load_policy
from sopvm.compiler.pipeline import compile_sop
from sopvm.ir.model import CompiledProgram
from sopvm.parser.errors import ParseError, SchemaValidationError, SemanticError


# --- Shared error handling --------------------------------------------------

class _CliError(Exception):
    """Expected CLI error (bad input, policy violation, etc.)."""
    def __init__(self, message: str, code: int = 2) -> None:
        self.message = message
        self.code = code
        super().__init__(message)


# --- Click group ------------------------------------------------------------

@click.group()
@click.version_option(package_name="sopvm")
def main() -> None:
    """SOPVM — compile and run Standard Operating Procedures."""


# --- compile ----------------------------------------------------------------

@main.command()
@click.argument("sop_path", type=click.Path(exists=True))
@click.option("--policy", "-p", required=True, type=click.Path(exists=True),
              help="Path to the policy YAML file.")
@click.option("-o", "--output", required=True, type=click.Path(),
              help="Output path for the compiled IR JSON.")
def compile(sop_path: str, policy: str, output: str) -> None:
    """Compile a SOP YAML into an IR JSON file."""
    try:
        program = compile_sop(sop_path, policy)
    except (ParseError, SchemaValidationError, SemanticError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(2)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(2)

    with open(output, "w", encoding="utf-8") as f:
        f.write(program.to_json())
    click.echo(f"Compiled to {output}", err=True)


# --- check ------------------------------------------------------------------

@main.command("check")
@click.argument("ir_path", type=click.Path(exists=True))
@click.option("--policy", "-p", required=True, type=click.Path(exists=True),
              help="Path to the policy YAML file.")
def check_cmd(ir_path: str, policy: str) -> None:
    """Check a compiled IR against a policy (pre-commit mode)."""
    from sopvm.checker.check import check as run_check

    try:
        program = CompiledProgram.from_json(open(ir_path, encoding="utf-8").read())
        pol = load_policy(policy)
        result = run_check(program, pol)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(2)

    if result.passed:
        click.echo("All capabilities within policy.", err=True)
        sys.exit(0)
    else:
        for v in result.violations:
            click.echo(
                f"VIOLATION step={v.step_id} requested={v.requested!r} "
                f"reason={v.reason}",
                err=True,
            )
        sys.exit(1)


# --- run --------------------------------------------------------------------

@main.command()
@click.argument("ir_path", type=click.Path(exists=True))
@click.option("--providers", "-r", type=click.Path(exists=True),
              help="Path to the providers YAML config.")
def run(ir_path: str, providers: str | None) -> None:
    """Execute a compiled SOP program."""
    from sopvm.integrations.langgraph.node import _SopvmHandler
    from sopvm.plugins.registry import ProviderRegistry
    from sopvm.runtime.executor import Executor
    from sopvm.runtime.state import StepState

    try:
        program = CompiledProgram.from_json(open(ir_path, encoding="utf-8").read())
    except Exception as e:
        click.echo(f"Error: failed to load IR: {e}", err=True)
        sys.exit(2)

    registry = ProviderRegistry()
    if providers:
        try:
            prov_config = yaml.safe_load(open(providers, encoding="utf-8"))
            for entry in (prov_config or []):
                import importlib
                mod = importlib.import_module(entry["module"])
                cls = getattr(mod, entry["class"])
                instance = cls(**entry.get("args", {}))
                registry.register(instance)
        except Exception as e:
            click.echo(f"Error: failed to load providers: {e}", err=True)
            sys.exit(2)

    handler = _SopvmHandler(registry)
    executor = Executor(
        program=program,
        handler=handler,
        registry=registry if providers else None,
    )
    result = executor.run()

    click.echo(f"Final state: {result.final_state.value}")
    click.echo(f"Path: {' -> '.join(result.path)}")
    if result.violation:
        click.echo(f"Violation: {result.violation.reason}", err=True)

    sys.exit(0 if result.final_state == StepState.DONE else 1)


# --- trace ------------------------------------------------------------------

@main.command()
@click.argument("log_path", type=click.Path(exists=True))
@click.argument("run_id")
def trace(log_path: str, run_id: str) -> None:
    """Pretty-print the telemetry trace for a given run_id."""
    found = False
    with open(log_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if record.get("run_id") == run_id:
                found = True
                event = record.get("event", "?")
                step = record.get("step_id", "")
                ts = record.get("timestamp", "")
                extra = {k: v for k, v in record.items()
                         if k not in ("event", "step_id", "timestamp", "run_id")}
                extra_str = f" {extra}" if extra else ""
                step_str = f" step={step}" if step else ""
                click.echo(f"[{ts}] {event}{step_str}{extra_str}")

    if not found:
        click.echo(f"No events found for run_id={run_id!r}", err=True)
        sys.exit(1)
