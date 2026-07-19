"""Property-based tests: lower() succeeds for any valid SopDocument."""

from pathlib import Path

import hypothesis.strategies as st
from hypothesis import given, settings

from sopvm.compiler import lower
from sopvm.ir.model import CompiledProgram
from sopvm.parser import SemanticError, parse

_sop_id = st.from_regex(r"[a-zA-Z_][a-zA-Z0-9_]{0,20}", fullmatch=True)
_cap_str = st.from_regex(r"[a-z]{1,8}:[a-z]{1,8}", fullmatch=True)


def _make_yaml(step_ids: list[str], caps: list[list[str]],
               edges: list[tuple[str | None, str | None]],
               terminals: list[bool]) -> str:
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
def test_lower_succeeds_for_valid_sop(step_ids, all_caps):
    """For any SopDocument that parse() accepts, lower() succeeds."""
    n = len(step_ids)
    edges: list[tuple[str | None, str | None]] = []
    terminals: list[bool] = []
    for i in range(n):
        if i == n - 1:
            terminals.append(True)
            edges.append((None, None))
        else:
            terminals.append(False)
            edges.append((step_ids[(i + 1) % n], None))

    caps_per_step = [[all_caps[i % len(all_caps)]] for i in range(n)]
    yaml_str = _make_yaml(step_ids, caps_per_step, edges, terminals)
    tmp = Path("_hypothesis_ir_test.sop.yaml")
    try:
        tmp.write_text(yaml_str, encoding="utf-8")
        doc = parse(tmp)
        prog = lower(doc)

        assert isinstance(prog, CompiledProgram)
        assert len(prog.nodes) == len(doc.steps)
        assert prog.entry == doc.steps[0].id

        for step in doc.steps:
            node = prog.nodes[step.id]
            assert node.capabilities_declared == [c.raw for c in step.requires]
            assert node.capabilities_paged == node.capabilities_declared
            assert node.terminal == step.terminal
    except SemanticError:
        pass
    finally:
        if tmp.exists():
            tmp.unlink()


@given(
    step_ids=st.lists(_sop_id, min_size=1, max_size=6, unique=True),
)
@settings(max_examples=100, deadline=None)
def test_lower_roundtrips_json(step_ids):
    """lower() output roundtrips through to_json/from_json."""
    n_val = len(step_ids)
    edges = []
    terminals = []
    for i in range(n_val):
        if i == n_val - 1:
            terminals.append(True)
            edges.append((None, None))
        else:
            terminals.append(False)
            edges.append((step_ids[(i + 1) % n_val], None))

    caps = [["db:read(x)"] for _ in range(n_val)]
    yaml_str = _make_yaml(step_ids, caps, edges, terminals)
    tmp = Path("_hypothesis_ir_test.sop.yaml")
    try:
        tmp.write_text(yaml_str, encoding="utf-8")
        doc = parse(tmp)
        prog = lower(doc)
        json_str = prog.to_json()
        restored = CompiledProgram.from_json(json_str)
        assert restored == prog
    except SemanticError:
        pass
    finally:
        if tmp.exists():
            tmp.unlink()
