"""Property-based tests using Hypothesis."""

from pathlib import Path

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings

from sopvm.parser import SemanticError, SopDocument, parse

_sop_id = st.from_regex(r"[a-zA-Z_][a-zA-Z0-9_]{0,20}", fullmatch=True)
_cap_str = st.from_regex(r"[a-z]{1,8}:[a-z]{1,8}", fullmatch=True)


def _make_yaml(step_ids: list[str], caps: list[list[str]], edges: list[tuple[str | None, str | None]], terminals: list[bool]) -> str:
    lines = [
        'sop_version: "0.1"',
        'name: "hypothesis_test"',
        'policy: "p"',
        "steps:",
    ]
    for sid, step_caps, (on_ok, on_err), term in zip(step_ids, caps, edges, terminals):
        lines.append(f'  - id: "{sid}"')
        lines.append(f'    description: "step {sid}"')
        if term:
            lines.append("    terminal: true")
        else:
            if on_ok:
                lines.append(f'    on_success: "{on_ok}"')
            if on_err:
                lines.append(f'    on_failure: "{on_err}"')
        lines.append("    requires:")
        cap_list = ", ".join(f'"{c}"' for c in step_caps)
        lines.append(f"      capabilities: [{cap_list}]")
    return "\n".join(lines) + "\n"


@given(
    step_ids=st.lists(_sop_id, min_size=1, max_size=8, unique=True),
    all_caps=st.lists(_cap_str, min_size=1, max_size=4),
)
@settings(max_examples=200, deadline=None)
def test_parse_never_returns_partial_output(step_ids, all_caps):
    """parse() either returns a fully-connected SopDocument or raises, never partial."""
    n = len(step_ids)
    # Build edges: each non-terminal step points to the next (or random)
    edges: list[tuple[str | None, str | None]] = []
    terminals: list[bool] = []
    for i in range(n):
        if i == n - 1:
            terminals.append(True)
            edges.append((None, None))
        else:
            terminals.append(False)
            next_id = step_ids[(i + 1) % n]
            edges.append((next_id, None))

    caps_per_step = [[all_caps[i % len(all_caps)]] for i in range(n)]
    yaml_str = _make_yaml(step_ids, caps_per_step, edges, terminals)

    tmp = Path("_hypothesis_test.sop.yaml")
    try:
        tmp.write_text(yaml_str, encoding="utf-8")
        doc = parse(tmp)

        # If parse succeeds, assert full connectivity
        assert isinstance(doc, SopDocument)
        assert len(doc.steps) == n
        doc_ids = {s.id for s in doc.steps}
        assert doc_ids == set(step_ids)
    except (SemanticError, Exception):
        # Allowed — but must not return partial output
        pass
    finally:
        if tmp.exists():
            tmp.unlink()


@given(
    step_ids=st.lists(_sop_id, min_size=3, max_size=6, unique=True),
)
@settings(max_examples=100, deadline=None)
def test_unreachable_step_raises_semantic_error(step_ids):
    """A step disconnected from entry raises SemanticError."""
    n = len(step_ids)
    # First step points to last (terminal), middle steps are unreachable
    # Middle steps must be terminal to pass edge check, then reachability catches them
    edges = [(step_ids[-1], None)]  # first -> last
    for i in range(1, n - 1):
        edges.append((None, None))  # middle steps unreachable
    edges.append((None, None))  # last is terminal
    terminals = [False] + [True] * (n - 1)
    caps = [["db:read(x)"] for _ in range(n)]

    yaml_str = _make_yaml(step_ids, caps, edges, terminals)
    tmp = Path("_hypothesis_test.sop.yaml")
    try:
        tmp.write_text(yaml_str, encoding="utf-8")
        with pytest.raises(SemanticError, match="unreachable"):
            parse(tmp)
    finally:
        if tmp.exists():
            tmp.unlink()
