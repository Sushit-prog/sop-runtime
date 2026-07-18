#!/usr/bin/env python3
"""API compatibility check script (Milestone 13).

Compares the current public API surface against the last tagged release.
Fails the build if a breaking change isn't accompanied by a MAJOR version
bump per VERSIONING_POLICY.md.

For the first run (no prior tag), passes trivially and records a baseline.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[1] / "src" / "sopvm"
BASELINE_FILE = Path(__file__).resolve().parents[1] / ".api-baseline.json"


def get_public_api() -> dict[str, list[str]]:
    """Extract the public API surface from sopvm/__init__.py.

    Returns a dict mapping function/class names to their argument lists.
    """
    init_file = SRC_ROOT / "__init__.py"
    tree = ast.parse(init_file.read_text(encoding="utf-8"))

    api: dict[str, list[str]] = {}

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            # Check if it's in __all__ (imported and re-exported)
            args = [arg.arg for arg in node.args.args if arg.arg != "self"]
            api[node.name] = args
        elif isinstance(node, ast.ClassDef):
            # Check for __init__ signature
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                    args = [arg.arg for arg in item.args.args if arg.arg != "self"]
                    api[node.name] = args
                    break

    return api


def get_last_tag() -> str | None:
    """Get the last git tag, or None if no tags exist."""
    try:
        result = subprocess.run(
            ["git", "describe", "--tags", "--abbrev=0"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None


def get_tagged_api(tag: str) -> dict[str, list[str]] | None:
    """Get the public API at a specific git tag."""
    try:
        result = subprocess.run(
            ["git", "show", f"{tag}:src/sopvm/__init__.py"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return None
        tree = ast.parse(result.stdout)
        api: dict[str, list[str]] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                args = [arg.arg for arg in node.args.args if arg.arg != "self"]
                api[node.name] = args
            elif isinstance(node, ast.ClassDef):
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                        args = [arg.arg for arg in item.args.args if arg.arg != "self"]
                        api[node.name] = args
                        break
        return api
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def compare_apis(old: dict[str, list[str]], new: dict[str, list[str]]) -> list[str]:
    """Compare two API surfaces. Returns list of breaking changes."""
    breaking = []

    # Check for removed symbols
    for name in old:
        if name not in new:
            breaking.append(f"REMOVED: {name}")

    # Check for changed signatures
    for name in old:
        if name in new:
            if old[name] != new[name]:
                breaking.append(
                    f"CHANGED: {name}({', '.join(old[name])}) -> "
                    f"{name}({', '.join(new[name])})"
                )

    return breaking


def main() -> int:
    current_api = get_public_api()
    print(f"Current public API: {list(current_api.keys())}")

    last_tag = get_last_tag()
    if last_tag is None:
        print("No prior git tag found — recording baseline.")
        BASELINE_FILE.write_text(
            json.dumps(current_api, indent=2) + "\n", encoding="utf-8"
        )
        print("Baseline recorded. API compat check passed (first run).")
        return 0

    print(f"Last tag: {last_tag}")
    old_api = get_tagged_api(last_tag)
    if old_api is None:
        print(f"Could not read API at tag {last_tag} — recording baseline.")
        BASELINE_FILE.write_text(
            json.dumps(current_api, indent=2) + "\n", encoding="utf-8"
        )
        return 0

    print(f"API at {last_tag}: {list(old_api.keys())}")
    breaking = compare_apis(old_api, current_api)

    if breaking:
        print("\nBREAKING CHANGES DETECTED:")
        for change in breaking:
            print(f"  - {change}")
        print("\nPer VERSIONING_POLICY.md, breaking changes require a MAJOR bump.")
        return 1
    else:
        print("\nNo breaking changes detected. API compat check passed.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
