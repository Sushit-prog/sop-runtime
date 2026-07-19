"""End-to-end demo: compile order-processing SOP and run with local LLM.

This script demonstrates the full SOPVM pipeline:
1. Compile a SOP with conditional branching
2. Run it with an LLM-backed StepHandler
3. Show capability gate enforcement in action

Requirements:
    pip install sopvm[llm-demo]
    # Download a model first — see examples/handlers/README.md

Usage:
    python examples/run_llm_demo.py
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Ensure examples/ is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run order-processing SOP with a local LLM handler"
    )
    parser.add_argument(
        "--model", "-m",
        default="models/Llama-3.2-1B-Instruct-Q4_K_M.gguf",
        help="Path to the GGUF model file"
    )
    parser.add_argument(
        "--sop",
        default="examples/sops/order-processing.sop.yaml",
        help="Path to the SOP YAML file"
    )
    parser.add_argument(
        "--policy",
        default="policies/order-processing.policy.yaml",
        help="Path to the policy YAML file"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging"
    )
    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    # Check model exists
    if not Path(args.model).exists():
        print(f"Error: Model file not found: {args.model}")
        print("See examples/handlers/README.md for download instructions.")
        return 1

    # Import here to avoid import errors when llama-cpp-python isn't installed
    try:
        from sopvm import compile
        from sopvm.runtime import Executor
        from examples.handlers.llm_handler import LlamaHandler
    except ImportError as e:
        print(f"Error: {e}")
        print("Install with: pip install sopvm[llm-demo]")
        return 1

    # Compile the SOP
    print(f"Compiling {args.sop}...")
    try:
        compiled = compile(args.sop, args.policy)
    except Exception as e:
        print(f"Compile error: {e}")
        return 1
    print(f"Compiled: {len(compiled.nodes)} nodes, entry={compiled.entry}")

    # Create the LLM handler
    handler = LlamaHandler(
        model_path=args.model,
        temperature=0.0,
        max_tokens=256,
    )

    # Run the SOP
    print("\nRunning SOP with local LLM handler...")
    print("=" * 60)
    executor = Executor(compiled, handler)
    try:
        result = executor.run()
    except Exception as e:
        print(f"Execution error: {e}")
        return 1

    # Print results
    print("=" * 60)
    print(f"Final state: {result.final_state.value}")
    print(f"Path: {' -> '.join(result.path)}")
    if result.violation:
        print(f"Violation: {result.violation.reason}")

    return 0 if result.final_state.value == "DONE" else 1


if __name__ == "__main__":
    sys.exit(main())
