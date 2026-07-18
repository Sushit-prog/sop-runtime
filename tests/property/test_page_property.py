"""Property-based tests for apply_paging."""

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings

from sopvm.capability.policy import Policy
from sopvm.capability.token import parse_capability
from sopvm.compiler.page import apply_paging
from sopvm.ir.model import CompiledProgram, IrNode

_cap_str = st.from_regex(r"[a-z]{1,8}:[a-z]{1,8}", fullmatch=True)


def _program(nodes: dict[str, list[str]]) -> CompiledProgram:
    ir_nodes = {}
    for sid, caps in nodes.items():
        ir_nodes[sid] = IrNode(
            capabilities_declared=list(caps),
            capabilities_paged=list(caps),
            edges={},
            terminal=True,
        )
    first = next(iter(nodes))
    return CompiledProgram(ir_version="0.1", entry=first, nodes=ir_nodes)


@given(
    step_ids=st.lists(
        st.from_regex(r"[a-z]{1,6}", fullmatch=True),
        min_size=1, max_size=6, unique=True,
    ),
    all_caps=st.lists(_cap_str, min_size=0, max_size=6),
    policy_caps=st.lists(_cap_str, min_size=0, max_size=6),
)
@settings(max_examples=200, deadline=None)
def test_paged_is_subset_of_declared(step_ids, all_caps, policy_caps):
    """capabilities_paged is always a subset of capabilities_declared."""
    nodes = {}
    for i, sid in enumerate(step_ids):
        caps = [all_caps[j % len(all_caps)] for j in range(max(1, len(all_caps) // len(step_ids)))] if all_caps else []
        nodes[sid] = caps

    prog = _program(nodes)
    policy = Policy(
        policy_version="0.1",
        allowed_capabilities=tuple(parse_capability(c) for c in policy_caps),
    )

    result = apply_paging(prog, policy)

    for sid in step_ids:
        declared = set(result.nodes[sid].capabilities_declared)
        paged = set(result.nodes[sid].capabilities_paged)
        assert paged <= declared, f"step {sid}: paged is not a subset of declared"


@given(
    step_ids=st.lists(
        st.from_regex(r"[a-z]{1,6}", fullmatch=True),
        min_size=1, max_size=6, unique=True,
    ),
    policy_caps=st.lists(_cap_str, min_size=0, max_size=6),
)
@settings(max_examples=200, deadline=None)
def test_paged_satisfies_policy(step_ids, policy_caps):
    """Every capability in capabilities_paged satisfies at least one policy entry."""
    nodes = {}
    for sid in step_ids:
        nodes[sid] = ["db:read(x)", "notify:email"]

    prog = _program(nodes)
    policy = Policy(
        policy_version="0.1",
        allowed_capabilities=tuple(parse_capability(c) for c in policy_caps),
    )

    result = apply_paging(prog, policy)

    from sopvm.checker.check import satisfies
    for sid in step_ids:
        for cap_str in result.nodes[sid].capabilities_paged:
            token = parse_capability(cap_str)
            assert any(satisfies(token, a) for a in policy.allowed_capabilities), \
                f"step {sid}: {cap_str!r} in paged but doesn't satisfy any policy entry"
