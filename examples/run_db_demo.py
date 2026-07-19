"""End-to-end demo: compile order-processing SOP and run with real SQLite provider.

This script demonstrates the full SOPVM pipeline with a real database:
1. Initialize a SQLite database with seed data
2. Compile the order-processing SOP
3. Run it with SqliteProvider wired in via ProviderRegistry
4. Print the trace and query the database to show real read/write happened

Usage:
    python examples/run_db_demo.py
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

# Ensure examples/ is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def print_table(db_path: Path, table: str) -> None:
    """Print all rows from a table."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(f"SELECT * FROM {table}").fetchall()
    conn.close()
    print(f"\n{table} table ({len(rows)} rows):")
    for row in rows:
        print(f"  {dict(row)}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run order-processing SOP with real SQLite provider"
    )
    parser.add_argument("--db", default="examples/providers/demo.db",
                        help="Path to SQLite database file")
    args = parser.parse_args()

    db_path = Path(args.db)

    # Step 1: Initialize the database
    print("=" * 60)
    print("Step 1: Initializing SQLite database")
    print("=" * 60)
    from examples.providers.init_demo_db import init_db
    init_db(db_path)
    print_table(db_path, "orders")

    # Step 2: Compile the SOP
    print("\n" + "=" * 60)
    print("Step 2: Compiling SOP")
    print("=" * 60)
    try:
        from sopvm import compile
        compiled = compile(
            "examples/sops/order-processing.sop.yaml",
            "policies/order-processing.policy.yaml",
        )
    except Exception as e:
        print(f"Compile error: {e}")
        return 1
    print(f"Compiled: {len(compiled.nodes)} nodes, entry={compiled.entry}")

    # Step 3: Wire up providers and run
    print("\n" + "=" * 60)
    print("Step 3: Running SOP with SqliteProvider")
    print("=" * 60)
    from sopvm.plugins.registry import ProviderRegistry
    from sopvm.runtime.executor import Executor
    from sopvm.runtime.state import StepState
    from examples.providers.sqlite_provider import SqliteProvider

    provider = SqliteProvider(db_path)
    registry = ProviderRegistry()
    registry.register(provider)
    print(f"Registered provider: {type(provider).__name__}")
    print(f"Declared capabilities: {provider.declared_capabilities()}")

    class DemoHandler:
        """Handler that invokes real tool calls for db capabilities.

        For conditional steps, checks the database to evaluate the
        condition. For db:read steps, reads from the database. For
        db:write steps, inserts a new row.
        """
        _order_counter = 4  # After seed data (Alice=1, Bob=2, Carol=3)

        def execute(self, node, request_tool=None):
            from sopvm.capability.token import parse_capability

            # Handle conditional steps: always route to auto_approve
            # (simulates "order is under $100") so the demo exercises db:write
            if node.condition:
                return StepState.FAILED

            # Handle db capability steps
            for cap_str in node.capabilities_declared:
                if cap_str.startswith("db:read("):
                    result = request_tool(parse_capability(cap_str), {})
                    if not result.success:
                        return StepState.FAILED
                elif cap_str.startswith("db:write("):
                    row = {
                        "customer": f"Customer-{DemoHandler._order_counter}",
                        "amount": 99.99,
                        "status": "approved",
                    }
                    DemoHandler._order_counter += 1
                    result = request_tool(parse_capability(cap_str), {
                        "action": "insert",
                        "row": row,
                    })
                    if not result.success:
                        return StepState.FAILED

            return StepState.DONE

    executor = Executor(compiled, DemoHandler(), registry=registry)
    result = executor.run()

    # Step 4: Print results
    print("\n" + "=" * 60)
    print("Step 4: Results")
    print("=" * 60)
    print(f"Final state: {result.final_state.value}")
    print(f"Path: {' -> '.join(result.path)}")
    if result.violation:
        print(f"Violation: {result.violation.reason}")

    # Step 5: Show database state after execution
    print_table(db_path, "orders")

    return 0 if result.final_state == StepState.DONE else 1


if __name__ == "__main__":
    sys.exit(main())
